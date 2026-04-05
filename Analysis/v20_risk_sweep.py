#!/usr/bin/env python3

from __future__ import annotations

import csv
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
TRADER_PATH = WORKSPACE_ROOT / "Bots" / "Traderv20_local.py"
BOT_DIR = WORKSPACE_ROOT / "Bots"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v20_sweep_runs"
REPORT_PATH = OUTPUT_DIR / "v20_sweep_report.txt"
CSV_PATH = OUTPUT_DIR / "v20_sweep_results.csv"
ENV_NAME = "TRADER_PARAM_OVERRIDES"
RANDOM_SEED = 20


def load_defaults() -> Dict[str, Dict[str, float]]:
    sys.path.insert(0, str(BOT_DIR))
    spec = importlib.util.spec_from_file_location("traderv20_local_sweep_module", TRADER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {TRADER_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        "EMERALDS": dict(module.DEFAULT_EMERALDS_PARAMS),
        "TOMATOES": dict(module.DEFAULT_TOMATOES_PARAMS),
    }


def clone_overrides(overrides: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    return {product: dict(values) for product, values in overrides.items()}


def run_backtest(run_id: str, overrides: Dict[str, Dict[str, float]], label: str) -> Dict[str, object]:
    run_dir = RUN_OUTPUT_ROOT / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)

    env = os.environ.copy()
    env[ENV_NAME] = json.dumps(overrides, separators=(",", ":"), sort_keys=True)

    command = [
        str(BACKTESTER),
        "--trader",
        str(TRADER_PATH),
        "--dataset",
        "workspace",
        "--day=-1",
        "--run-id",
        run_id,
        "--artifact-mode",
        "none",
        "--products",
        "off",
        "--output-root",
        str(RUN_OUTPUT_ROOT),
    ]

    completed = subprocess.run(
        command,
        cwd=WORKSPACE_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        raise RuntimeError(
            f"Missing metrics for {run_id}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    with metrics_path.open() as handle:
        metrics = json.load(handle)

    by_product = metrics.get("final_pnl_by_product", {})
    return {
        "run_id": run_id,
        "label": label,
        "total": float(metrics["final_pnl_total"]),
        "emeralds": float(by_product.get("EMERALDS", 0.0)),
        "tomatoes": float(by_product.get("TOMATOES", 0.0)),
        "trade_count": int(metrics.get("own_trade_count", 0)),
        "overrides": clone_overrides(overrides),
    }


def make_case(base: Dict[str, Dict[str, float]], label: str, updates: Dict[str, float]) -> Dict[str, object]:
    overrides = clone_overrides(base)
    overrides.setdefault("TOMATOES", {}).update(updates)
    return {"label": label, "overrides": overrides}


def build_cases(defaults: Dict[str, Dict[str, float]]) -> List[Dict[str, object]]:
    base = clone_overrides(defaults)
    cases: List[Dict[str, object]] = [
        {"label": "baseline_v20", "overrides": base},
        make_case(
            base,
            "carry_light",
            {
                "INVENTORY_SKEW": 0.045,
                "SOFT_LIMIT_RATIO": 0.65,
                "POSITION_BIAS_DIVISOR": 14.0,
                "TREND_ENTRY_TAKE_BONUS": 2.0,
                "TREND_HOLD_EXIT_BONUS": 0.40,
                "STRONG_TREND_HOLD_EXIT_BONUS": 0.70,
            },
        ),
        make_case(
            base,
            "carry_heavy",
            {
                "INVENTORY_SKEW": 0.02,
                "SOFT_LIMIT_RATIO": 0.85,
                "POSITION_BIAS_DIVISOR": 10.0,
                "MAX_TAKE_SIZE": 12,
                "TREND_ENTRY_TAKE_BONUS": 5.0,
                "TREND_HOLD_EXIT_BONUS": 0.80,
                "STRONG_TREND_HOLD_EXIT_BONUS": 1.20,
                "PASSIVE_SIZE": 10,
            },
        ),
        make_case(
            base,
            "lower_drag_faster_entry",
            {
                "INVENTORY_SKEW": 0.025,
                "TREND_EDGE_THRESHOLD": 1.0,
                "FIT_THRESHOLD": 0.45,
                "BASE_TAKE_EDGE": 1.20,
                "MAX_TAKE_SIZE": 12,
                "TREND_ENTRY_TAKE_BONUS": 4.0,
            },
        ),
        make_case(
            base,
            "slower_exits",
            {
                "TREND_HOLD_EXIT_BONUS": 0.80,
                "STRONG_TREND_HOLD_EXIT_BONUS": 1.20,
                "SOFT_LIMIT_RATIO": 0.80,
                "INVENTORY_SKEW": 0.03,
            },
        ),
        make_case(
            base,
            "wide_bands_cleaner",
            {
                "SOFT_LIMIT_RATIO": 0.90,
                "POSITION_BIAS_DIVISOR": 10.0,
                "PASSIVE_SIZE": 10,
                "MAX_TAKE_SIZE": 12,
                "TREND_PASSIVE_SIZE_BONUS": 3.0,
                "TREND_PASSIVE_PUSH": 2.0,
            },
        ),
        make_case(
            base,
            "aggressive_balanced",
            {
                "INVENTORY_SKEW": 0.03,
                "BASE_TAKE_EDGE": 1.20,
                "PASSIVE_SIZE": 10,
                "MAX_TAKE_SIZE": 12,
                "TREND_EDGE_THRESHOLD": 1.0,
                "FIT_THRESHOLD": 0.50,
                "SOFT_LIMIT_RATIO": 0.82,
                "POSITION_BIAS_DIVISOR": 11.0,
                "TREND_ENTRY_TAKE_BONUS": 4.0,
                "TREND_HOLD_EXIT_BONUS": 0.70,
                "STRONG_TREND_HOLD_EXIT_BONUS": 1.00,
            },
        ),
    ]

    rng = random.Random(RANDOM_SEED)
    sampled = set()
    while len(sampled) < 36:
        combo = (
            rng.choice([0.02, 0.03, 0.035, 0.045, 0.06]),   # INVENTORY_SKEW
            rng.choice([1.10, 1.20, 1.30, 1.45, 1.60]),     # BASE_TAKE_EDGE
            rng.choice([8, 9, 10, 11]),                     # PASSIVE_SIZE
            rng.choice([8, 10, 12, 14]),                    # MAX_TAKE_SIZE
            rng.choice([1.0, 1.2, 1.4]),                    # TREND_EDGE_THRESHOLD
            rng.choice([2.5, 3.0, 3.5, 4.0]),               # STRONG_TREND_EDGE
            rng.choice([0.45, 0.55, 0.65]),                 # FIT_THRESHOLD
            rng.choice([0.65, 0.72, 0.82, 0.90]),           # SOFT_LIMIT_RATIO
            rng.choice([10.0, 12.0, 14.0, 16.0]),           # POSITION_BIAS_DIVISOR
            rng.choice([0.15, 0.25, 0.35]),                 # TREND_FAIR_BONUS
            rng.choice([2.0, 3.0, 4.0, 5.0]),               # TREND_ENTRY_TAKE_BONUS
            rng.choice([0.30, 0.55, 0.80]),                 # TREND_HOLD_EXIT_BONUS
            rng.choice([0.60, 0.90, 1.20]),                 # STRONG_TREND_HOLD_EXIT_BONUS
            rng.choice([0.0, 1.0, 2.0]),                    # TREND_PASSIVE_PUSH
            rng.choice([1.0, 2.0, 3.0]),                    # TREND_PASSIVE_SIZE_BONUS
        )
        sampled.add(combo)

    for index, combo in enumerate(sorted(sampled), start=1):
        (
            inventory_skew,
            base_take_edge,
            passive_size,
            max_take_size,
            trend_edge_threshold,
            strong_trend_edge,
            fit_threshold,
            soft_limit_ratio,
            position_bias_divisor,
            trend_fair_bonus,
            trend_entry_take_bonus,
            trend_hold_exit_bonus,
            strong_trend_hold_exit_bonus,
            trend_passive_push,
            trend_passive_size_bonus,
        ) = combo
        cases.append(
            make_case(
                base,
                f"risk_random_{index:02d}",
                {
                    "INVENTORY_SKEW": inventory_skew,
                    "BASE_TAKE_EDGE": base_take_edge,
                    "PASSIVE_SIZE": passive_size,
                    "MAX_TAKE_SIZE": max_take_size,
                    "TREND_EDGE_THRESHOLD": trend_edge_threshold,
                    "STRONG_TREND_EDGE": strong_trend_edge,
                    "FIT_THRESHOLD": fit_threshold,
                    "SOFT_LIMIT_RATIO": soft_limit_ratio,
                    "POSITION_BIAS_DIVISOR": position_bias_divisor,
                    "TREND_FAIR_BONUS": trend_fair_bonus,
                    "TREND_ENTRY_TAKE_BONUS": trend_entry_take_bonus,
                    "TREND_HOLD_EXIT_BONUS": trend_hold_exit_bonus,
                    "STRONG_TREND_HOLD_EXIT_BONUS": strong_trend_hold_exit_bonus,
                    "TREND_PASSIVE_PUSH": trend_passive_push,
                    "TREND_PASSIVE_SIZE_BONUS": trend_passive_size_bonus,
                },
            )
        )

    return cases


def write_csv(results: List[Dict[str, object]]) -> None:
    with CSV_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "run_id",
                "label",
                "total_pnl",
                "emeralds_pnl",
                "tomatoes_pnl",
                "trade_count",
                "overrides_json",
            ]
        )
        for row in results:
            writer.writerow(
                [
                    row["run_id"],
                    row["label"],
                    f"{row['total']:.1f}",
                    f"{row['emeralds']:.1f}",
                    f"{row['tomatoes']:.1f}",
                    row["trade_count"],
                    json.dumps(row["overrides"]["TOMATOES"], sort_keys=True),
                ]
            )


def write_report(results: List[Dict[str, object]]) -> None:
    baseline = next(row for row in results if row["label"] == "baseline_v20")
    ordered = sorted(results, key=lambda row: (row["total"], row["tomatoes"], row["emeralds"]), reverse=True)
    top = ordered[:12]

    lines = [
        "V20 Risk Sweep",
        "",
        "Method",
        "- Rust backtester on workspace day -1",
        f"- Trader: {TRADER_PATH.name}",
        "- Search style: higher-risk TOMATOES carry sweep on top of V20",
        f"- Random seed: {RANDOM_SEED}",
        "- Important note: use this for local direction, not as an official PnL estimate",
        "",
        "Baseline",
        f"- Total: {baseline['total']:.1f}",
        f"- EMERALDS: {baseline['emeralds']:.1f}",
        f"- TOMATOES: {baseline['tomatoes']:.1f}",
        "",
        "Top Results",
    ]

    for row in top:
        delta = row["total"] - baseline["total"]
        lines.extend(
            [
                f"- {row['label']}: total {row['total']:.1f} ({delta:+.1f} vs baseline), TOMATOES {row['tomatoes']:.1f}, EMERALDS {row['emeralds']:.1f}, trades {row['trade_count']}",
                f"  overrides: {json.dumps(row['overrides']['TOMATOES'], sort_keys=True)}",
            ]
        )

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    if not BACKTESTER.exists():
        raise FileNotFoundError(f"Backtester binary not found: {BACKTESTER}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    defaults = load_defaults()
    cases = build_cases(defaults)
    results: List[Dict[str, object]] = []

    for index, case in enumerate(cases, start=1):
        run_id = f"v20-sweep-{index:03d}"
        result = run_backtest(run_id, case["overrides"], str(case["label"]))
        results.append(result)

    write_csv(results)
    write_report(results)

    baseline = next(row for row in results if row["label"] == "baseline_v20")
    best = max(results, key=lambda row: (row["total"], row["tomatoes"], row["emeralds"]))
    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {CSV_PATH}")
    print(f"Baseline {baseline['total']:.1f} -> best {best['total']:.1f} ({best['label']})")


if __name__ == "__main__":
    main()
