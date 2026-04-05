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
TRADER_PATH = WORKSPACE_ROOT / "Bots" / "Traderv18_local.py"
BOT_DIR = WORKSPACE_ROOT / "Bots"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v18_sweep_runs"
REPORT_PATH = OUTPUT_DIR / "v18_sweep_report.txt"
CSV_PATH = OUTPUT_DIR / "v18_sweep_results.csv"
ENV_NAME = "TRADER_PARAM_OVERRIDES"
RANDOM_SEED = 18


def load_defaults() -> Dict[str, Dict[str, float]]:
    sys.path.insert(0, str(BOT_DIR))
    spec = importlib.util.spec_from_file_location("traderv18_local_sweep_module", TRADER_PATH)
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
        {"label": "baseline_v18", "overrides": base},
        make_case(
            base,
            "predictive_soft",
            {
                "REGRESSION_WEIGHT": 0.15,
                "RESIDUAL_REVERT_WEIGHT": 0.10,
                "REGRESSION_HORIZON": 1.0,
                "TREND_EDGE_THRESHOLD": 1.75,
                "FIT_THRESHOLD": 0.70,
                "BASE_TAKE_EDGE": 1.45,
                "BASE_QUOTE_EDGE": 2.25,
            },
        ),
        make_case(
            base,
            "predictive_strong",
            {
                "REGRESSION_WEIGHT": 0.35,
                "RESIDUAL_REVERT_WEIGHT": 0.05,
                "REGRESSION_HORIZON": 2.5,
                "TREND_EDGE_THRESHOLD": 1.25,
                "FIT_THRESHOLD": 0.55,
                "BASE_TAKE_EDGE": 1.35,
                "BASE_QUOTE_EDGE": 2.50,
            },
        ),
        make_case(
            base,
            "range_lean",
            {
                "REGRESSION_WEIGHT": 0.10,
                "RESIDUAL_REVERT_WEIGHT": 0.20,
                "TREND_EDGE_THRESHOLD": 2.25,
                "FIT_THRESHOLD": 0.75,
                "BASE_TAKE_EDGE": 1.60,
                "BASE_QUOTE_EDGE": 2.00,
            },
        ),
        make_case(
            base,
            "trend_lean",
            {
                "REGRESSION_WEIGHT": 0.30,
                "RESIDUAL_REVERT_WEIGHT": 0.00,
                "REGRESSION_HORIZON": 2.0,
                "TREND_EDGE_THRESHOLD": 1.25,
                "FIT_THRESHOLD": 0.55,
                "TREND_IMBALANCE_THRESHOLD": 0.08,
                "BASE_TAKE_EDGE": 1.35,
                "BASE_QUOTE_EDGE": 2.50,
            },
        ),
        make_case(
            base,
            "faster_horizon",
            {
                "REGRESSION_HORIZON": 1.0,
                "REGRESSION_WEIGHT": 0.25,
                "BASE_TAKE_EDGE": 1.35,
                "BASE_QUOTE_EDGE": 2.25,
            },
        ),
        make_case(
            base,
            "slower_horizon",
            {
                "REGRESSION_HORIZON": 3.0,
                "REGRESSION_WEIGHT": 0.30,
                "BASE_TAKE_EDGE": 1.55,
                "BASE_QUOTE_EDGE": 2.75,
            },
        ),
    ]

    rng = random.Random(RANDOM_SEED)
    sampled = set()
    while len(sampled) < 28:
        combo = (
            rng.choice([0.10, 0.15, 0.20, 0.30, 0.40]),  # REGRESSION_WEIGHT
            rng.choice([0.00, 0.08, 0.12, 0.20]),        # RESIDUAL_REVERT_WEIGHT
            rng.choice([1.0, 1.5, 2.0, 2.5, 3.0]),       # REGRESSION_HORIZON
            rng.choice([1.25, 1.50, 1.75, 2.25]),        # TREND_EDGE_THRESHOLD
            rng.choice([0.55, 0.65, 0.75]),              # FIT_THRESHOLD
            rng.choice([0.08, 0.12, 0.18]),              # TREND_IMBALANCE_THRESHOLD
            rng.choice([1.25, 1.35, 1.45, 1.60]),        # BASE_TAKE_EDGE
            rng.choice([2.00, 2.25, 2.50, 2.75]),        # BASE_QUOTE_EDGE
            rng.choice([6, 8, 10]),                      # PASSIVE_SIZE
            rng.choice([6, 8, 10]),                      # MAX_TAKE_SIZE
        )
        sampled.add(combo)

    for index, combo in enumerate(sorted(sampled), start=1):
        (
            regression_weight,
            residual_revert_weight,
            regression_horizon,
            trend_edge_threshold,
            fit_threshold,
            trend_imbalance_threshold,
            base_take_edge,
            base_quote_edge,
            passive_size,
            max_take_size,
        ) = combo
        cases.append(
            make_case(
                base,
                f"regression_random_{index:02d}",
                {
                    "REGRESSION_WEIGHT": regression_weight,
                    "RESIDUAL_REVERT_WEIGHT": residual_revert_weight,
                    "REGRESSION_HORIZON": regression_horizon,
                    "TREND_EDGE_THRESHOLD": trend_edge_threshold,
                    "FIT_THRESHOLD": fit_threshold,
                    "TREND_IMBALANCE_THRESHOLD": trend_imbalance_threshold,
                    "BASE_TAKE_EDGE": base_take_edge,
                    "BASE_QUOTE_EDGE": base_quote_edge,
                    "PASSIVE_SIZE": passive_size,
                    "MAX_TAKE_SIZE": max_take_size,
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
    baseline = next(row for row in results if row["label"] == "baseline_v18")
    ordered = sorted(results, key=lambda row: (row["total"], row["tomatoes"], row["emeralds"]), reverse=True)
    top = ordered[:10]

    lines = [
        "V18 Regression Sweep",
        "",
        "Method",
        "- Rust backtester on workspace day -1",
        f"- Trader: {TRADER_PATH.name}",
        "- Search style: regression-model sweep for TOMATOES only",
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
        run_id = f"v18-sweep-{index:03d}"
        result = run_backtest(run_id, case["overrides"], str(case["label"]))
        results.append(result)

    write_csv(results)
    write_report(results)

    baseline = next(row for row in results if row["label"] == "baseline_v18")
    best = max(results, key=lambda row: (row["total"], row["tomatoes"], row["emeralds"]))
    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {CSV_PATH}")
    print(f"Baseline {baseline['total']:.1f} -> best {best['total']:.1f} ({best['label']})")


if __name__ == "__main__":
    main()
