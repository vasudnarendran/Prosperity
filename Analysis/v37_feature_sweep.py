#!/usr/bin/env python3
"""
Focused local sweep around Traderv37's book-delta breakout parameters.

This is intentionally narrower than the older full CMA-ES runs. The goal is to
find locally safe variants of the new v37 breakout layer without tuning away the
official simulator edge that v37 just introduced.

Usage:
    python3 Analysis/v37_feature_sweep.py
    python3 Analysis/v37_feature_sweep.py --samples 48 --keep-top 12
    python3 Analysis/v37_feature_sweep.py --samples 6 --skip-coordinate --output-prefix v37_feature_sweep_smoke

Outputs:
    Analysis/output/<prefix>_results.json
    Analysis/output/<prefix>_candidates.csv
    Analysis/output/<prefix>_report.txt
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE_PATH = Path(
    "/Users/vasudravinarendran/Documents/Prosperity/MyProsperity/Bots/Traderv37.py"
)
BACKTESTER = ROOT / "Backtest_failed_Python" / "run_backtest.py"
OUTPUT_DIR = ROOT / "Analysis" / "output"

PARAM_NAMES = [
    "BOOK_ACTIVITY_FLOOR",
    "BOOK_STEP_WEIGHT",
    "BOOK_DEPLETION_WEIGHT",
    "MICRO_DRIFT_WEIGHT",
    "PRESSURE_BIAS_SCALE",
    "BREAKOUT_FOLLOW_SCALE",
    "BREAKOUT_QUOTE_TIGHTEN",
    "BREAKOUT_HOLD_BONUS",
]

PARAM_BOUNDS: Dict[str, tuple[float, float]] = {
    "BOOK_ACTIVITY_FLOOR": (0.30, 1.20),
    "BOOK_STEP_WEIGHT": (0.40, 1.50),
    "BOOK_DEPLETION_WEIGHT": (0.25, 1.20),
    "MICRO_DRIFT_WEIGHT": (0.15, 1.10),
    "PRESSURE_BIAS_SCALE": (0.05, 0.50),
    "BREAKOUT_FOLLOW_SCALE": (0.05, 0.40),
    "BREAKOUT_QUOTE_TIGHTEN": (0.02, 0.45),
    "BREAKOUT_HOLD_BONUS": (0.02, 0.30),
}

PARAM_WINDOWS: Dict[str, float] = {
    "BOOK_ACTIVITY_FLOOR": 0.18,
    "BOOK_STEP_WEIGHT": 0.25,
    "BOOK_DEPLETION_WEIGHT": 0.22,
    "MICRO_DRIFT_WEIGHT": 0.18,
    "PRESSURE_BIAS_SCALE": 0.08,
    "BREAKOUT_FOLLOW_SCALE": 0.07,
    "BREAKOUT_QUOTE_TIGHTEN": 0.08,
    "BREAKOUT_HOLD_BONUS": 0.06,
}

_eval_count = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Focused local sweep for Traderv37 breakout parameters.")
    parser.add_argument(
        "--samples",
        type=int,
        default=32,
        help="Number of random focused candidates to evaluate in addition to the baseline and coordinate probes.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=37,
        help="Random seed for focused sampling.",
    )
    parser.add_argument(
        "--keep-top",
        type=int,
        default=10,
        help="How many top candidates to include in the report summary.",
    )
    parser.add_argument(
        "--output-prefix",
        default="v37_feature_sweep",
        help="Filename prefix for output artifacts inside Analysis/output.",
    )
    parser.add_argument(
        "--skip-coordinate",
        action="store_true",
        help="Skip the one-at-a-time coordinate probes and run random candidates only.",
    )
    return parser.parse_args()


def extract_tomatoes_block(source: str) -> tuple[int, int, str]:
    marker = "DEFAULT_TOMATOES_PARAMS = {"
    start = source.find(marker)
    if start == -1:
        raise ValueError("DEFAULT_TOMATOES_PARAMS not found in source")

    brace_depth = 0
    end = start
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
            if brace_depth == 0:
                end = index + 1
                break

    return start, end, source[start:end]


def extract_defaults(source: str) -> Dict[str, float]:
    _start, _end, block = extract_tomatoes_block(source)
    defaults: Dict[str, float] = {}
    for name in PARAM_NAMES:
        match = re.search(rf'"{re.escape(name)}":\s*([\d.eE+\-]+)', block)
        if not match:
            raise ValueError(f"{name} not found inside DEFAULT_TOMATOES_PARAMS")
        defaults[name] = float(match.group(1))
    return defaults


def inject_params(source: str, params: Dict[str, float]) -> str:
    start, end, block = extract_tomatoes_block(source)

    for name, value in params.items():
        pattern = rf'("{re.escape(name)}":\s*)[\d.eE+\-]+'
        replacement = rf"\g<1>{value:.8g}"
        block = re.sub(pattern, replacement, block)

    return source[:start] + block + source[end:]


def clamp(name: str, value: float) -> float:
    lo, hi = PARAM_BOUNDS[name]
    return max(lo, min(hi, value))


def fingerprint(params: Dict[str, float]) -> tuple[float, ...]:
    return tuple(round(params[name], 6) for name in PARAM_NAMES)


def build_coordinate_candidates(defaults: Dict[str, float]) -> List[Dict[str, object]]:
    candidates: List[Dict[str, object]] = []
    for name in PARAM_NAMES:
        step = PARAM_WINDOWS[name] * 0.5
        for direction, suffix in ((-1.0, "down"), (1.0, "up")):
            value = clamp(name, defaults[name] + direction * step)
            if abs(value - defaults[name]) <= 1e-9:
                continue
            params = dict(defaults)
            params[name] = value
            candidates.append(
                {
                    "label": f"coord_{name.lower()}_{suffix}",
                    "family": "coordinate",
                    "params": params,
                }
            )
    return candidates


def build_random_candidates(
    defaults: Dict[str, float],
    samples: int,
    seed: int,
    seen: set[tuple[float, ...]],
) -> List[Dict[str, object]]:
    rng = random.Random(seed)
    candidates: List[Dict[str, object]] = []
    attempts = 0

    while len(candidates) < samples:
        attempts += 1
        if attempts > max(200, samples * 50):
            break

        params = {}
        for name in PARAM_NAMES:
            lo, hi = PARAM_BOUNDS[name]
            center = defaults[name]
            window = PARAM_WINDOWS[name]
            sample_lo = max(lo, center - window)
            sample_hi = min(hi, center + window)
            params[name] = rng.triangular(sample_lo, center, sample_hi)

        key = fingerprint(params)
        if key in seen:
            continue

        seen.add(key)
        candidates.append(
            {
                "label": f"random_{len(candidates) + 1:03d}",
                "family": "random",
                "params": params,
            }
        )

    return candidates


def parse_backtest_summary(stdout: str) -> Dict[str, object]:
    total_pnl = None
    product_pnl: Dict[str, float] = {}
    product_position: Dict[str, int] = {}

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("Final total PnL:"):
            total_pnl = float(line.split(":", 1)[1].strip())
            continue

        match = re.match(
            r"^- ([A-Z_]+): ([\d.\-]+) \| final position (-?\d+)$",
            line,
        )
        if match:
            product = match.group(1)
            product_pnl[product] = float(match.group(2))
            product_position[product] = int(match.group(3))

    if total_pnl is None:
        raise RuntimeError(f"Could not parse Final total PnL from backtest output:\n{stdout}")

    return {
        "total_pnl": total_pnl,
        "product_pnl": product_pnl,
        "product_position": product_position,
    }


def run_with_params(source: str, params: Dict[str, float], day: int) -> Dict[str, object]:
    global _eval_count
    _eval_count += 1

    tmp_stem = f"v37_sweep_{uuid.uuid4().hex}"
    tmp_dir = Path(tempfile.gettempdir())
    tmp_bot = tmp_dir / f"{tmp_stem}.py"
    tmp_out = tmp_dir / tmp_stem

    try:
        patched = inject_params(source, params)
        if not patched.endswith("\n"):
            patched += "\n"
        tmp_bot.write_text(patched)

        result = subprocess.run(
            [
                sys.executable,
                str(BACKTESTER),
                str(tmp_bot),
                "--day",
                str(day),
                "--output",
                str(tmp_out),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Backtester failed for day {day} with code {result.returncode}:\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

        return parse_backtest_summary(result.stdout)
    finally:
        if tmp_bot.exists():
            tmp_bot.unlink()
        if tmp_out.exists():
            shutil.rmtree(tmp_out, ignore_errors=True)


def score_candidate(
    day1_total: float,
    day2_total: float,
    baseline_day1: float,
    baseline_day2: float,
) -> float:
    avg_total = (day1_total + day2_total) / 2.0
    regression_penalty = (
        1.35 * max(0.0, baseline_day1 - day1_total)
        + 1.35 * max(0.0, baseline_day2 - day2_total)
    )
    imbalance_penalty = 0.10 * abs(day1_total - day2_total)
    return avg_total - regression_penalty - imbalance_penalty


def evaluate_candidate(
    source: str,
    label: str,
    family: str,
    params: Dict[str, float],
    baseline_day1: float,
    baseline_day2: float,
) -> Dict[str, object]:
    day1 = run_with_params(source, params, day=-1)
    day2 = run_with_params(source, params, day=-2)

    day1_total = float(day1["total_pnl"])
    day2_total = float(day2["total_pnl"])
    avg_total = (day1_total + day2_total) / 2.0
    score = score_candidate(day1_total, day2_total, baseline_day1, baseline_day2)

    return {
        "label": label,
        "family": family,
        "params": {name: round(params[name], 8) for name in PARAM_NAMES},
        "score": round(score, 4),
        "day_neg1_total": round(day1_total, 4),
        "day_neg2_total": round(day2_total, 4),
        "avg_total": round(avg_total, 4),
        "delta_day_neg1": round(day1_total - baseline_day1, 4),
        "delta_day_neg2": round(day2_total - baseline_day2, 4),
        "delta_avg_total": round(avg_total - (baseline_day1 + baseline_day2) / 2.0, 4),
        "day_neg1_tomatoes": round(day1["product_pnl"].get("TOMATOES", 0.0), 4),
        "day_neg2_tomatoes": round(day2["product_pnl"].get("TOMATOES", 0.0), 4),
        "day_neg1_emeralds": round(day1["product_pnl"].get("EMERALDS", 0.0), 4),
        "day_neg2_emeralds": round(day2["product_pnl"].get("EMERALDS", 0.0), 4),
    }


def write_outputs(
    prefix: str,
    defaults: Dict[str, float],
    baseline: Dict[str, object],
    results: List[Dict[str, object]],
    keep_top: int,
    samples: int,
    seed: int,
    skip_coordinate: bool,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUTPUT_DIR / f"{prefix}_results.json"
    csv_path = OUTPUT_DIR / f"{prefix}_candidates.csv"
    report_path = OUTPUT_DIR / f"{prefix}_report.txt"

    by_score = sorted(results, key=lambda item: item["score"], reverse=True)
    by_avg = sorted(results, key=lambda item: item["avg_total"], reverse=True)
    top_score = by_score[:keep_top]
    top_avg = by_avg[:keep_top]

    payload = {
        "meta": {
            "bot_source_path": str(BOT_SOURCE_PATH),
            "backtester": str(BACKTESTER),
            "samples_random": samples,
            "seed": seed,
            "skip_coordinate": skip_coordinate,
            "total_candidates": len(results),
            "total_evaluations": _eval_count,
            "note": (
                "Local filter only. Traderv37 improved officially while underperforming locally, "
                "so top candidates should be validated on the official simulator before adoption."
            ),
        },
        "defaults": defaults,
        "search_space": {
            name: {
                "bounds": list(PARAM_BOUNDS[name]),
                "window": PARAM_WINDOWS[name],
            }
            for name in PARAM_NAMES
        },
        "baseline": baseline,
        "top_by_score": top_score,
        "top_by_avg_total": top_avg,
        "results": by_score,
    }
    json_path.write_text(json.dumps(payload, indent=2))

    fieldnames = [
        "label",
        "family",
        "score",
        "day_neg1_total",
        "day_neg2_total",
        "avg_total",
        "delta_day_neg1",
        "delta_day_neg2",
        "delta_avg_total",
        "day_neg1_tomatoes",
        "day_neg2_tomatoes",
        "day_neg1_emeralds",
        "day_neg2_emeralds",
    ] + PARAM_NAMES
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in by_score:
            row = {key: result.get(key) for key in fieldnames}
            for name in PARAM_NAMES:
                row[name] = result["params"][name]
            writer.writerow(row)

    baseline_avg = (baseline["day_neg1_total"] + baseline["day_neg2_total"]) / 2.0
    lines = [
        "V37 Focused Feature Sweep Report",
        "================================",
        "",
        f"Bot source: {BOT_SOURCE_PATH}",
        f"Backtester: {BACKTESTER}",
        f"Random samples: {samples}",
        f"Coordinate probes: {'disabled' if skip_coordinate else 'enabled'}",
        f"Total candidates: {len(results)}",
        f"Total evaluations: {_eval_count}",
        "",
        "Why This Sweep Exists",
        "---------------------",
        "Traderv37 is the first breakout branch that changed the official simulator path,",
        "but it still underperforms locally. This sweep searches narrowly around the new",
        "book-delta controls and ranks candidates by a regression-aware local score rather",
        "than trying to replace v37 with a broad local optimum.",
        "",
        "Current Traderv37 Local Baseline",
        "--------------------------------",
        f"Day -1 total: {baseline['day_neg1_total']:.2f}",
        f"Day -2 total: {baseline['day_neg2_total']:.2f}",
        f"Avg total:    {baseline_avg:.2f}",
        f"Day -1 TOMATOES: {baseline['day_neg1_tomatoes']:.2f}",
        f"Day -2 TOMATOES: {baseline['day_neg2_tomatoes']:.2f}",
        "",
        "Tracked Parameters",
        "------------------",
    ]
    for name in PARAM_NAMES:
        lo, hi = PARAM_BOUNDS[name]
        lines.append(
            f"{name}: default={defaults[name]:.4f}, bounds=({lo:.4f}, {hi:.4f}), window=+/-{PARAM_WINDOWS[name]:.4f}"
        )

    lines += [
        "",
        "Top Candidates By Local Score",
        "-----------------------------",
        f"{'Rank':>4}  {'Label':<30} {'Score':>10} {'Avg':>10} {'D1 Delta':>10} {'D2 Delta':>10}",
    ]
    for rank, result in enumerate(top_score, start=1):
        lines.append(
            f"{rank:4d}  {result['label']:<30} {result['score']:10.2f} "
            f"{result['avg_total']:10.2f} {result['delta_day_neg1']:10.2f} {result['delta_day_neg2']:10.2f}"
        )

    lines += [
        "",
        "Top Candidates By Raw Average",
        "-----------------------------",
        f"{'Rank':>4}  {'Label':<30} {'Avg':>10} {'Score':>10} {'D1 Total':>10} {'D2 Total':>10}",
    ]
    for rank, result in enumerate(top_avg, start=1):
        lines.append(
            f"{rank:4d}  {result['label']:<30} {result['avg_total']:10.2f} "
            f"{result['score']:10.2f} {result['day_neg1_total']:10.2f} {result['day_neg2_total']:10.2f}"
        )

    lines += [
        "",
        "Recommendation",
        "--------------",
        "Use this as a local filter only.",
        "Start official testing with the top 3-5 candidates by local score, not the entire list.",
        "If a candidate matches or beats v37 officially, then run a second, tighter sweep around that point.",
    ]

    report_path.write_text("\n".join(lines) + "\n")

    print(f"\nWrote {json_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {report_path}")


def main() -> None:
    args = parse_args()

    if not BOT_SOURCE_PATH.exists():
        raise FileNotFoundError(f"Bot not found: {BOT_SOURCE_PATH}")
    if not BACKTESTER.exists():
        raise FileNotFoundError(f"Backtester not found: {BACKTESTER}")

    source = BOT_SOURCE_PATH.read_text()
    defaults = extract_defaults(source)

    print("Running current Traderv37 baseline on both local days ...")
    baseline_day1 = run_with_params(source, defaults, day=-1)
    baseline_day2 = run_with_params(source, defaults, day=-2)
    baseline = {
        "day_neg1_total": round(float(baseline_day1["total_pnl"]), 4),
        "day_neg2_total": round(float(baseline_day2["total_pnl"]), 4),
        "avg_total": round(
            (float(baseline_day1["total_pnl"]) + float(baseline_day2["total_pnl"])) / 2.0,
            4,
        ),
        "day_neg1_tomatoes": round(baseline_day1["product_pnl"].get("TOMATOES", 0.0), 4),
        "day_neg2_tomatoes": round(baseline_day2["product_pnl"].get("TOMATOES", 0.0), 4),
    }
    print(
        f"Baseline | day -1={baseline['day_neg1_total']:.2f} | "
        f"day -2={baseline['day_neg2_total']:.2f} | avg={baseline['avg_total']:.2f}"
    )

    seen = {fingerprint(defaults)}
    candidates: List[Dict[str, object]] = []
    if not args.skip_coordinate:
        for candidate in build_coordinate_candidates(defaults):
            key = fingerprint(candidate["params"])
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    candidates.extend(build_random_candidates(defaults, args.samples, args.seed, seen))

    print(
        f"Evaluating {len(candidates)} focused candidates "
        f"({'random only' if args.skip_coordinate else 'coordinate + random'}) ..."
    )

    results: List[Dict[str, object]] = []
    total = len(candidates)
    for index, candidate in enumerate(candidates, start=1):
        result = evaluate_candidate(
            source=source,
            label=str(candidate["label"]),
            family=str(candidate["family"]),
            params=dict(candidate["params"]),
            baseline_day1=float(baseline["day_neg1_total"]),
            baseline_day2=float(baseline["day_neg2_total"]),
        )
        results.append(result)
        print(
            f"[{index:02d}/{total:02d}] {result['label']:<30} "
            f"score={result['score']:8.2f} "
            f"avg={result['avg_total']:8.2f} "
            f"d1={result['delta_day_neg1']:+7.2f} "
            f"d2={result['delta_day_neg2']:+7.2f}"
        )

    write_outputs(
        prefix=args.output_prefix,
        defaults=defaults,
        baseline=baseline,
        results=results,
        keep_top=args.keep_top,
        samples=args.samples,
        seed=args.seed,
        skip_coordinate=args.skip_coordinate,
    )

    print("\nDone.")
    print(f"Total evals: {_eval_count}")


if __name__ == "__main__":
    main()
