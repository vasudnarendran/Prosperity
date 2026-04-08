from __future__ import annotations

from importlib import metadata

from prosperity4mcbt._version import __version__ as bundled_version


def current_version() -> str:
    # Release bundles run directly from an extracted source tree, so prefer the
    # bundled version marker when it has been stamped during packaging.
    if bundled_version and not bundled_version.endswith("+local"):
        return bundled_version

    try:
        return metadata.version("prosperity4mcbt")
    except metadata.PackageNotFoundError:
        return bundled_version
