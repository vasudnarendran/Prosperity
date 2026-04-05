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
TRADER_PATH = WORKSPACE_ROOT / "Bots" / "Traderv17_local.py"
BOT_DIR = WORKSPACE_ROOT / "Bots"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v17_coarse_runs"
REPORT_PATH = OUTPUT_DIR / "v17_coarse_report.txt"
CSV_PATH = OUTPUT_DIR / "v17_coarse_results.csv"
ENV_NAME = "TRADER_PARAM_OVERRIDES"
RANDOM_SEED = 17


def load_defaults() -> Dict[str, Dict[str, float]]:
    sys.path.insert(0, str(BOT_DIR))
    spec = importlib.util.spec_from_file_location("traderv17_local_sweep_module", TRADER_PATH)
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
        {"label": "baseline_v17", "overrides": base},
        make_case(
            base,
            "pressure_off_maker",
            {
                "PRESSURE_MICRO_COEF": 0.0,
                "PRESSURE_SHORT_MOMENTUM_COEF": 0.0,
                "PRESSURE_IMBALANCE_COEF": 0.0,
                "PRESSURE_FAIR_BONUS": 0.0,
                "PRESSURE_EDGE_BONUS": 0.0,
                "PRESSURE_QUOTE_THRESHOLD": 99.0,
                "BASE_QUOTE_EDGE": 2.75,
                "BASE_TAKE_EDGE": 1.45,
            },
        ),
        make_case(
            base,
            "pressure_off_taker",
            {
                "PRESSURE_MICRO_COEF": 0.0,
                "PRESSURE_SHORT_MOMENTUM_COEF": 0.0,
                "PRESSURE_IMBALANCE_COEF": 0.0,
                "PRESSURE_FAIR_BONUS": 0.0,
                "PRESSURE_EDGE_BONUS": 0.0,
                "PRESSURE_QUOTE_THRESHOLD": 99.0,
                "BASE_QUOTE_EDGE": 2.0,
                "BASE_TAKE_EDGE": 1.1,
                "MAX_TAKE_SIZE": 10,
            },
        ),
        make_case(
            base,
            "light_pressure_balanced",
            {
                "PRESSURE_MICRO_COEF": 0.6,
                "PRESSURE_SHORT_MOMENTUM_COEF": 0.35,
                "PRESSURE_IMBALANCE_COEF": 1.8,
                "PRESSURE_FAIR_BONUS": 0.15,
                "PRESSURE_EDGE_BONUS": 0.0,
                "PRESSURE_QUOTE_THRESHOLD": 1.6,
                "BASE_QUOTE_EDGE": 2.5,
                "BASE_TAKE_EDGE": 1.35,
            },
        ),
        make_case(
            base,
            "strong_pressure_trend",
            {
                "PRESSURE_MICRO_COEF": 1.4,
                "PRESSURE_SHORT_MOMENTUM_COEF": 0.8,
                "PRESSURE_IMBALANCE_COEF": 3.0,
                "PRESSURE_FAIR_BONUS": 1.0,
                "PRESSURE_EDGE_BONUS": 0.35,
                "PRESSURE_QUOTE_THRESHOLD": 0.8,
                "BASE_QUOTE_EDGE": 2.0,
                "BASE_TAKE_EDGE": 1.1,
            },
        ),
        make_case(
            base,
            "wide_quote_low_take",
            {
                "BASE_QUOTE_EDGE": 3.0,
                "BASE_TAKE_EDGE": 1.0,
                "PRESSURE_MICRO_COEF": 0.3,
                "PRESSURE_FAIR_BONUS": 0.0,
                "PRESSURE_EDGE_BONUS": 0.0,
            },
        ),
        make_case(
            base,
            "narrow_quote_high_take",
            {
                "BASE_QUOTE_EDGE": 1.75,
                "BASE_TAKE_EDGE": 1.85,
                "PRESSURE_MICRO_COEF": 0.6,
                "PRESSURE_FAIR_BONUS": 0.15,
            },
        ),
        make_case(
            base,
            "imbalance_only",
            {
                "PRESSURE_MICRO_COEF": 0.0,
                "PRESSURE_SHORT_MOMENTUM_COEF": 0.0,
                "PRESSURE_IMBALANCE_COEF": 2.8,
                "PRESSURE_FAIR_BONUS": 0.2,
                "PRESSURE_EDGE_BONUS": 0.0,
                "PRESSURE_QUOTE_THRESHOLD": 1.2,
                "BASE_TAKE_EDGE": 1.35,
                "BASE_QUOTE_EDGE": 2.5,
            },
        ),
        make_case(
            base,
            "short_momo_only",
            {
                "PRESSURE_MICRO_COEF": 0.0,
                "PRESSURE_SHORT_MOMENTUM_COEF": 0.8,
                "PRESSURE_IMBALANCE_COEF": 0.0,
                "PRESSURE_FAIR_BONUS": 0.25,
                "PRESSURE_EDGE_BONUS": 0.0,
                "PRESSURE_QUOTE_THRESHOLD": 1.2,
                "BASE_TAKE_EDGE": 1.35,
                "BASE_QUOTE_EDGE": 2.5,
            },
        ),
    ]

    rng = random.Random(RANDOM_SEED)
    sampled = set()
    while len(sampled) < 30:
        combo = (
            rng.choice([1.0, 1.15, 1.35, 1.6, 1.85]),
            rng.choice([1.75, 2.0, 2.5, 3.0]),
            rng.choice([0.0, 0.3, 0.6, 1.0, 1.5]),
            rng.choice([0.0, 0.15, 0.35, 0.6, 0.9]),
            rng.choice([0.0, 0.8, 1.8, 2.8, 3.5]),
            rng.choice([0.0, 0.15, 0.5, 1.0]),
            rng.choice([0.0, 0.1, 0.25, 0.4]),
            rng.choice([0.8, 1.2, 1.6, 2.2]),
            rng.choice([6, 8, 10]),
            rng.choice([6, 8, 10]),
        )
        sampled.add(combo)

    for index, combo in enumerate(sorted(sampled), start=1):
        (
            base_take_edge,
            base_quote_edge,
            pressure_micro,
            pressure_short,
            pressure_imbalance,
            pressure_fair_bonus,
            pressure_edge_bonus,
            pressure_quote_threshold,
            passive_size,
            max_take_size,
        ) = combo
        cases.append(
            make_case(
                base,
                f"coarse_random_{index:02d}",
                {
                    "BASE_TAKE_EDGE": base_take_edge,
                    "BASE_QUOTE_EDGE": base_quote_edge,
                    "PRESSURE_MICRO_COEF": pressure_micro,
                    "PRESSURE_SHORT_MOMENTUM_COEF": pressure_short,
                    "PRESSURE_IMBALANCE_COEF": pressure_imbalance,
                    "PRESSURE_FAIR_BONUS": pressure_fair_bonus,
                    "PRESSURE_EDGE_BONUS": pressure_edge_bonus,
                    "PRESSURE_QUOTE_THRESHOLD": pressure_quote_threshold,
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
                ]
            )


def write_report(results: List[Dict[str, object]]) -> None:
    baseline = next(row for row in results if row["label"] == "baseline_v17")
    ordered = sorted(results, key=lambda row: (row["total"], row["tomatoes"], row["emeralds"]), reverse=True)
    top = ordered[:10]

    lines = [
        "V17 Coarse Sweep",
        "",
        "Method",
        "- Rust backtester on workspace day -1",
        f"- Trader: {TRADER_PATH.name}",
        "- Search style: wider-steps architecture sweep plus random coarse sampling",
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
        run_id = f"v17-coarse-{index:03d}"
        result = run_backtest(run_id, case["overrides"], str(case["label"]))
        results.append(result)

    write_csv(results)
    write_report(results)

    baseline = next(row for row in results if row["label"] == "baseline_v17")
    best = max(results, key=lambda row: (row["total"], row["tomatoes"], row["emeralds"]))
    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {CSV_PATH}")
    print(f"Baseline {baseline['total']:.1f} -> best {best['total']:.1f} ({best['label']})")


if __name__ == "__main__":
    main()
