from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from prosperity4mcbt.version import current_version


LATEST_RELEASE_URL = "https://api.github.com/repos/chrispyroberts/imc-prosperity-4/releases/latest"
COMPARE_URL_TEMPLATE = "https://api.github.com/repos/chrispyroberts/imc-prosperity-4/compare/{base}...{head}"
CACHE_TTL = timedelta(hours=12)
REQUEST_TIMEOUT_SECONDS = 2.0


@dataclass
class LatestRelease:
    tag_name: str
    name: str
    html_url: str
    published_at: str


@dataclass
class ReleaseStatus:
    state: str
    current_version: str
    current_sha: Optional[str]
    latest: Optional[LatestRelease]
    recommendation: str
    detail: str
    checked_at: str
    error: Optional[str] = None


def _is_repo_root(path: Path) -> bool:
    return (path / "backtester" / "prosperity4mcbt").is_dir() and (path / "rust_simulator").is_dir()


def _is_release_root(path: Path) -> bool:
    return (path / "prosperity4mcbt").is_dir() and (path / "bin").is_dir()


def project_root() -> Path:
    root_env = os.environ.get("PROSPERITY4MCBT_ROOT")
    if root_env:
        candidate = Path(root_env).resolve()
        if _is_repo_root(candidate) or _is_release_root(candidate):
            return candidate

    here = Path(__file__).resolve()
    for candidate in here.parents:
        if _is_repo_root(candidate) or _is_release_root(candidate):
            return candidate

    return here.parents[2]


def cache_path() -> Path:
    return Path.home() / ".prosperity4mcbt" / "release_check.json"


def installed_version() -> str:
    return current_version()


def built_binary_path() -> Path:
    root = project_root()
    if _is_release_root(root):
        binary_name = "prosperity4_sim.exe" if sys.platform.startswith("win") else "prosperity4_sim"
        return root / "bin" / binary_name

    binary_name = "rust_simulator.exe" if sys.platform.startswith("win") else "rust_simulator"
    return root / "rust_simulator" / "target" / "release" / binary_name


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _http_get_json(url: str) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "prosperity4mcbt",
        },
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.load(response)


def _git_output(*args: str) -> Optional[str]:
    root = project_root()
    if not (root / ".git").exists():
        return None

    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def _git_is_ancestor(older: str, newer: str) -> bool:
    root = project_root()
    if not (root / ".git").exists():
        return False

    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _semver_tuple(value: str) -> Optional[tuple[int, int, int]]:
    token = value.strip()
    if token.startswith("v"):
        token = token[1:]
    core = token.split("+", 1)[0].split("-", 1)[0]
    parts = core.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def _is_dev_build(version: str) -> bool:
    return version.endswith("+local") or version == "0.0.0"


def _fetch_latest_release() -> LatestRelease:
    payload = _http_get_json(LATEST_RELEASE_URL)
    return LatestRelease(
        tag_name=payload["tag_name"],
        name=payload.get("name") or payload["tag_name"],
        html_url=payload["html_url"],
        published_at=payload["published_at"],
    )


def _fetch_compare_status(base_tag: str, head_sha: str) -> Optional[str]:
    url = COMPARE_URL_TEMPLATE.format(base=quote(base_tag), head=quote(head_sha))
    payload = _http_get_json(url)
    status = payload.get("status")
    return status if isinstance(status, str) else None


def _status_from_compare(latest: LatestRelease, current_version: str, current_sha: str) -> Optional[ReleaseStatus]:
    try:
        compare_status = _fetch_compare_status(latest.tag_name, current_sha)
    except (HTTPError, URLError, TimeoutError, OSError):
        return None

    checked_at = _utc_now().isoformat()
    if compare_status in {"identical", "ahead"}:
        detail = f"Current checkout includes the latest release {latest.tag_name}."
        if compare_status == "ahead":
            detail = f"Current checkout is ahead of the latest release {latest.tag_name}."
        return ReleaseStatus(
            state="up_to_date",
            current_version=current_version,
            current_sha=current_sha,
            latest=latest,
            recommendation="No update needed.",
            detail=detail,
            checked_at=checked_at,
        )
    if compare_status == "behind":
        return ReleaseStatus(
            state="update_available",
            current_version=current_version,
            current_sha=current_sha,
            latest=latest,
            recommendation="Update recommended before leaderboard runs.",
            detail=f"Current checkout is behind the latest release {latest.tag_name}.",
            checked_at=checked_at,
        )
    if compare_status == "diverged":
        return ReleaseStatus(
            state="diverged",
            current_version=current_version,
            current_sha=current_sha,
            latest=latest,
            recommendation="Review the latest release before updating this checkout.",
            detail=f"Current checkout diverges from the latest release {latest.tag_name}.",
            checked_at=checked_at,
        )
    return None


def _status_from_tracking_branch(latest: LatestRelease, current_version: str, current_sha: str) -> Optional[ReleaseStatus]:
    branch_name = _git_output("rev-parse", "--abbrev-ref", "HEAD")
    if branch_name in {None, "HEAD"}:
        return None

    remote_ref = f"origin/{branch_name}"
    remote_sha = _git_output("rev-parse", remote_ref)
    if remote_sha is None:
        return None

    try:
        branch_compare_status = _fetch_compare_status(latest.tag_name, branch_name)
    except (HTTPError, URLError, TimeoutError, OSError):
        return None

    checked_at = _utc_now().isoformat()
    if current_sha == remote_sha or _git_is_ancestor(remote_sha, current_sha):
        if branch_compare_status in {"identical", "ahead"}:
            detail = f"Tracked branch {remote_ref} includes the latest release {latest.tag_name}."
            if current_sha != remote_sha:
                detail = f"Current checkout is ahead of {remote_ref}, which already includes {latest.tag_name}."
            return ReleaseStatus(
                state="up_to_date",
                current_version=current_version,
                current_sha=current_sha,
                latest=latest,
                recommendation="No update needed.",
                detail=detail,
                checked_at=checked_at,
            )
        if branch_compare_status == "behind":
            return ReleaseStatus(
                state="unknown",
                current_version=current_version,
                current_sha=current_sha,
                latest=latest,
                recommendation="Unable to determine automatically whether this ahead-of-branch checkout should be updated.",
                detail=f"Tracked branch {remote_ref} is behind {latest.tag_name}, but the local checkout is ahead of the branch.",
                checked_at=checked_at,
            )

    if _git_is_ancestor(current_sha, remote_sha):
        if branch_compare_status in {"identical", "ahead"}:
            return ReleaseStatus(
                state="update_available",
                current_version=current_version,
                current_sha=current_sha,
                latest=latest,
                recommendation="Update recommended before leaderboard runs.",
                detail=f"Local checkout is behind {remote_ref}, and that branch already includes {latest.tag_name}.",
                checked_at=checked_at,
            )
        if branch_compare_status == "behind":
            return ReleaseStatus(
                state="update_available",
                current_version=current_version,
                current_sha=current_sha,
                latest=latest,
                recommendation="Update recommended before leaderboard runs.",
                detail=f"Local checkout is behind {remote_ref}, and that branch is still behind {latest.tag_name}.",
                checked_at=checked_at,
            )

    return None


def _status_from_version(latest: LatestRelease, current_version: str, current_sha: Optional[str]) -> ReleaseStatus:
    current_semver = _semver_tuple(current_version)
    latest_semver = _semver_tuple(latest.tag_name)
    checked_at = _utc_now().isoformat()

    if current_semver is None or latest_semver is None:
        return ReleaseStatus(
            state="unknown",
            current_version=current_version,
            current_sha=current_sha,
            latest=latest,
            recommendation="Unable to determine whether you should update automatically.",
            detail="Version strings are not comparable.",
            checked_at=checked_at,
        )

    if current_semver < latest_semver:
        return ReleaseStatus(
            state="update_available",
            current_version=current_version,
            current_sha=current_sha,
            latest=latest,
            recommendation="Update recommended before leaderboard runs.",
            detail=f"Installed version {current_version} is older than {latest.tag_name}.",
            checked_at=checked_at,
        )
    if current_semver > latest_semver:
        return ReleaseStatus(
            state="up_to_date",
            current_version=current_version,
            current_sha=current_sha,
            latest=latest,
            recommendation="No update needed.",
            detail=f"Installed version {current_version} is newer than the latest published release {latest.tag_name}.",
            checked_at=checked_at,
        )
    return ReleaseStatus(
        state="up_to_date",
        current_version=current_version,
        current_sha=current_sha,
        latest=latest,
        recommendation="No update needed.",
        detail=f"Installed version matches the latest release {latest.tag_name}.",
        checked_at=checked_at,
    )


def _compute_release_status() -> ReleaseStatus:
    current_version = installed_version()
    current_sha = _git_output("rev-parse", "HEAD")

    try:
        latest = _fetch_latest_release()
    except (HTTPError, URLError, TimeoutError, OSError, KeyError, ValueError) as exc:
        return ReleaseStatus(
            state="unknown",
            current_version=current_version,
            current_sha=current_sha,
            latest=None,
            recommendation="Unable to check for updates right now.",
            detail="Latest release lookup failed.",
            checked_at=_utc_now().isoformat(),
            error=str(exc),
        )

    if current_sha is not None:
        compared = _status_from_compare(latest, current_version, current_sha)
        if compared is not None:
            return compared
        tracked_branch = _status_from_tracking_branch(latest, current_version, current_sha)
        if tracked_branch is not None:
            return tracked_branch
        if _is_dev_build(current_version):
            return ReleaseStatus(
                state="unknown",
                current_version=current_version,
                current_sha=current_sha,
                latest=latest,
                recommendation="Unable to verify whether this local checkout should be updated automatically.",
                detail="This looks like a development checkout, and release ancestry could not be verified.",
                checked_at=_utc_now().isoformat(),
            )

    return _status_from_version(latest, current_version, current_sha)


def _load_cached_status() -> Optional[ReleaseStatus]:
    path = cache_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        checked_at = datetime.fromisoformat(payload["checked_at"])
        if _utc_now() - checked_at > CACHE_TTL:
            return None
        latest_payload = payload.get("latest")
        latest = LatestRelease(**latest_payload) if latest_payload else None
        return ReleaseStatus(
            state=payload["state"],
            current_version=payload["current_version"],
            current_sha=payload.get("current_sha"),
            latest=latest,
            recommendation=payload["recommendation"],
            detail=payload["detail"],
            checked_at=payload["checked_at"],
            error=payload.get("error"),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _save_cached_status(status: ReleaseStatus) -> None:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(status)
    path.write_text(json.dumps(payload), encoding="utf-8")


def get_release_status(force: bool = False) -> ReleaseStatus:
    if not force:
        cached = _load_cached_status()
        if cached is not None:
            return cached

    status = _compute_release_status()
    try:
        _save_cached_status(status)
    except OSError:
        pass
    return status


def format_update_notice(status: ReleaseStatus) -> Optional[str]:
    if status.state != "update_available" or status.latest is None:
        return None
    return (
        f"Update available: {status.latest.tag_name}.\n"
        f"{status.detail}\n"
        f"Recommendation: {status.recommendation}\n"
        f"Release: {status.latest.html_url}"
    )


def _check_line(label: str, ok: bool, detail: str) -> str:
    status = "OK" if ok else "WARN"
    return f"{label:<20} {status:<4} {detail}"


def build_self_test_report(force_release_check: bool = True) -> str:
    root = project_root()
    simulator_dir = root / "rust_simulator"
    binary = built_binary_path()
    release_bundle = _is_release_root(root)
    cargo_path = shutil.which("cargo")
    cargo_version = None
    if cargo_path:
        cargo_version = subprocess.run(
            [cargo_path, "--version"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip() or cargo_path

    release = get_release_status(force=force_release_check)
    lines = [
        "prosperity4mcbt self-test",
        _check_line("Package version", True, installed_version()),
        _check_line("Python", True, sys.version.split()[0]),
        _check_line("Project root", root.exists(), str(root)),
        _check_line(
            "Rust source",
            simulator_dir.is_dir() or release_bundle,
            "not required in a release bundle" if release_bundle else str(simulator_dir),
        ),
        _check_line("Release binary", binary.is_file(), str(binary)),
        _check_line(
            "Cargo",
            cargo_path is not None or release_bundle,
            cargo_version or ("not required in a release bundle" if release_bundle else "cargo not found"),
        ),
    ]

    if release.latest is not None:
        published = release.latest.published_at.replace("T", " ").replace("Z", " UTC")
        lines.append(_check_line("Latest release", True, f"{release.latest.tag_name} ({published})"))
        lines.append(_check_line("Release status", release.state != "unknown", release.detail))
        lines.append(f"Recommendation       {release.recommendation}")
        lines.append(f"Release URL          {release.latest.html_url}")
    else:
        lines.append(_check_line("Latest release", False, release.error or release.detail))
        lines.append(f"Recommendation       {release.recommendation}")

    if release.current_sha:
        lines.append(f"Git HEAD             {release.current_sha}")

    return "\n".join(lines)
