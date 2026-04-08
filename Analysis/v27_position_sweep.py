#!/usr/bin/env python3
"""
V27 position-limit sweep using the Python backtester.
Sweeps TOMATOES position sizing parameters + offline blend weights.
Runs both day -1 and day -2, ranks by average PnL.

Usage (from repo root):
    python3 Analysis/v27_position_sweep.py
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from itertools import product as iterproduct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT = Path("/Users/vasudravinarendran/Documents/Prosperity/MyProsperity/Bots/Traderv27.py")
BACKTESTER = ROOT / "Backtest_failed_Python" / "run_backtest.py"
OUTPUT_DIR = ROOT / "Analysis" / "output"
REPORT_PATH = OUTPUT_DIR / "v27_sweep_report.txt"
CSV_PATH = OUTPUT_DIR / "v27_sweep_results.csv"

DAYS = [-1, -2]


def run_case(overrides: dict, day: int) -> float:
    env = os.environ.copy()
    env["TRADER_PARAM_OVERRIDES"] = json.dumps({"TOMATOES": overrides})

    result = subprocess.run(
        [sys.executable, str(BACKTESTER), str(BOT), "--day", str(day)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    for line in result.stdout.splitlines():
        if line.startswith("Final total PnL:"):
            return float(line.split(":")[1].strip())

    raise RuntimeError(f"No PnL found for day {day}.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")


def build_cases() -> list[dict]:
    cases = []

    # Baseline (V27 defaults)
    cases.append({"label": "baseline", "overrides": {}})

    # Grid sweep over key position sizing parameters
    soft_limits = [0.65, 0.75, 0.85]
    passive_bonuses = [2.0, 3.0, 4.0]
    max_takes = [10, 12, 15]
    short_blends = [0.65, 0.80, 0.95]
    long_blends = [0.30, 0.45, 0.60]

    # Focused combos: vary soft_limit + passive_bonus together (most impactful pair)
    for sl, pb in iterproduct(soft_limits, passive_bonuses):
        if sl == 0.65 and pb == 2.0:
            continue  # that's the baseline
        cases.append({
            "label": f"sl{int(sl*100)}_pb{int(pb*10)}",
            "overrides": {"SOFT_LIMIT_RATIO": sl, "TREND_PASSIVE_SIZE_BONUS": pb},
        })

    # Vary max_take_size with best soft_limit candidates
    for mt in [12, 15]:
        cases.append({
            "label": f"sl85_pb40_mt{mt}",
            "overrides": {"SOFT_LIMIT_RATIO": 0.85, "TREND_PASSIVE_SIZE_BONUS": 4.0, "MAX_TAKE_SIZE": mt},
        })

    # Vary offline blend weights
    for sb, lb in iterproduct(short_blends, long_blends):
        if sb == 0.80 and lb == 0.45:
            continue  # that's the baseline
        cases.append({
            "label": f"sb{int(sb*100)}_lb{int(lb*100)}",
            "overrides": {"OFFLINE_SHORT_BLEND": sb, "OFFLINE_LONG_BLEND": lb},
        })

    # Combined best guesses
    cases.append({
        "label": "combined_aggressive",
        "overrides": {
            "SOFT_LIMIT_RATIO": 0.85,
            "TREND_PASSIVE_SIZE_BONUS": 4.0,
            "MAX_TAKE_SIZE": 12,
            "OFFLINE_SHORT_BLEND": 0.95,
            "OFFLINE_LONG_BLEND": 0.45,
        },
    })
    cases.append({
        "label": "combined_balanced",
        "overrides": {
            "SOFT_LIMIT_RATIO": 0.75,
            "TREND_PASSIVE_SIZE_BONUS": 3.0,
            "MAX_TAKE_SIZE": 12,
            "OFFLINE_SHORT_BLEND": 0.80,
            "OFFLINE_LONG_BLEND": 0.60,
        },
    })

    return cases


def main() -> None:
    if not BOT.exists():
        raise FileNotFoundError(f"Bot not found: {BOT}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    results = []

    total = len(cases)
    for idx, case in enumerate(cases, 1):
        label = case["label"]
        overrides = case["overrides"]
        print(f"[{idx}/{total}] {label} ...", end=" ", flush=True)

        day_pnls = {}
        for day in DAYS:
            pnl = run_case(overrides, day)
            day_pnls[day] = pnl

        avg = sum(day_pnls.values()) / len(DAYS)
        print(f"day-1={day_pnls[-1]:.0f}  day-2={day_pnls[-2]:.0f}  avg={avg:.0f}")

        results.append({
            "label": label,
            "day_m1": day_pnls[-1],
            "day_m2": day_pnls[-2],
            "avg": avg,
            "overrides": overrides,
        })

    baseline_avg = next(r["avg"] for r in results if r["label"] == "baseline")
    results.sort(key=lambda r: r["avg"], reverse=True)

    # Write CSV
    with CSV_PATH.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["label", "day_m1", "day_m2", "avg", "delta_vs_baseline", "overrides_json"])
        for r in results:
            writer.writerow([
                r["label"],
                f"{r['day_m1']:.1f}",
                f"{r['day_m2']:.1f}",
                f"{r['avg']:.1f}",
                f"{r['avg'] - baseline_avg:+.1f}",
                json.dumps(r["overrides"], sort_keys=True),
            ])

    # Write report
    lines = [
        "V27 Position Sweep Report",
        "=========================",
        f"Bot: {BOT}",
        f"Cases: {total}",
        f"Days: {DAYS}",
        "",
        f"Baseline avg: {baseline_avg:.1f}",
        "",
        "Top 10 results:",
    ]
    for r in results[:10]:
        delta = r["avg"] - baseline_avg
        lines.append(
            f"  {r['label']}: avg={r['avg']:.1f} ({delta:+.1f}) | "
            f"day-1={r['day_m1']:.1f} day-2={r['day_m2']:.1f}"
        )
        if r["overrides"]:
            lines.append(f"    overrides: {json.dumps(r['overrides'], sort_keys=True)}")

    REPORT_PATH.write_text("\n".join(lines) + "\n")

    print()
    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {CSV_PATH}")
    best = results[0]
    print(f"Best: {best['label']}  avg={best['avg']:.1f}  ({best['avg']-baseline_avg:+.1f} vs baseline)")


if __name__ == "__main__":
    main()
