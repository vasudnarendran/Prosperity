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
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
TRADER_PATH = WORKSPACE_ROOT / "Bots" / "Traderv29_1a_local.py"
BOT_DIR = WORKSPACE_ROOT / "Bots"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v29_1a_plateau_runs"
REPORT_PATH = OUTPUT_DIR / "v29_1a_plateau_report.txt"
CSV_PATH = OUTPUT_DIR / "v29_1a_plateau_results.csv"
ENV_NAME = "TRADER_PARAM_OVERRIDES"
RANDOM_SEED = 2910

BASE_TOMATOES = {
    "BASE_QUOTE_EDGE": 2.65,
    "SPREAD_VOL_COEF": 0.84,
    "SPREAD_INV_COEF": 0.38,
    "SPREAD_TIME_COEF": 0.82,
    "BASE_TAKE_EDGE": 1.25,
    "ALPHA_EDGE_SCALE": 1.06,
    "ALPHA_IMBALANCE_SCALE": 1.16,
    "ALPHA_THRESHOLD_SCALE": 1.03,
    "TREND_SELL_HOLD_EXTRA": 0.24,
    "TREND_QUOTE_LIFT_EXTRA": 1.0,
    "TREND_BUY_TAKE_EXTRA": 0.08,
    "RESERVATION_SCALE": 0.12,
    "TREND_RESERVATION_BIAS": 0.04,
    "RANGE_RESERVATION_BIAS": 0.20,
}


def load_defaults() -> Dict[str, Dict[str, float]]:
    sys.path.insert(0, str(BOT_DIR))
    spec = importlib.util.spec_from_file_location("traderv29_1a_local_module", TRADER_PATH)
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


def make_case(base: Dict[str, Dict[str, float]], label: str, family: str, updates: Dict[str, float]) -> Dict[str, object]:
    overrides = clone_overrides(base)
    overrides.setdefault("TOMATOES", {}).update(updates)
    return {"label": label, "family": family, "overrides": overrides}


def build_cases(defaults: Dict[str, Dict[str, float]]) -> List[Dict[str, object]]:
    base = clone_overrides(defaults)
    base["TOMATOES"].update(BASE_TOMATOES)

    cases: List[Dict[str, object]] = [
        {"label": "baseline_v29_1a", "family": "baseline", "overrides": base},
        make_case(
            base,
            "spread_plus_small",
            "designed",
            {
                "BASE_QUOTE_EDGE": 2.75,
                "SPREAD_VOL_COEF": 0.90,
                "SPREAD_INV_COEF": 0.42,
                "SPREAD_TIME_COEF": 0.90,
            },
        ),
        make_case(
            base,
            "spread_plus_balanced",
            "designed",
            {
                "BASE_QUOTE_EDGE": 2.70,
                "SPREAD_VOL_COEF": 0.88,
                "SPREAD_INV_COEF": 0.40,
                "SPREAD_TIME_COEF": 0.86,
                "BASE_TAKE_EDGE": 1.20,
            },
        ),
        make_case(
            base,
            "quote_alpha_blend",
            "designed",
            {
                "BASE_QUOTE_EDGE": 2.70,
                "ALPHA_IMBALANCE_SCALE": 1.22,
                "ALPHA_EDGE_SCALE": 1.08,
                "TREND_QUOTE_LIFT_EXTRA": 2.0,
            },
        ),
        make_case(
            base,
            "reservation_tight",
            "designed",
            {
                "RESERVATION_SCALE": 0.14,
                "TREND_RESERVATION_BIAS": 0.06,
                "RANGE_RESERVATION_BIAS": 0.18,
                "BASE_TAKE_EDGE": 1.20,
            },
        ),
        make_case(
            base,
            "sell_patience_light",
            "designed",
            {
                "TREND_SELL_HOLD_EXTRA": 0.28,
                "TREND_QUOTE_LIFT_EXTRA": 2.0,
                "HOLD_TIME_COEF": 0.12,
            },
        ),
        make_case(
            base,
            "quote_take_mix",
            "designed",
            {
                "BASE_QUOTE_EDGE": 2.75,
                "BASE_TAKE_EDGE": 1.20,
                "SPREAD_VOL_COEF": 0.88,
                "TREND_BUY_TAKE_EXTRA": 0.12,
            },
        ),
    ]

    rng = random.Random(RANDOM_SEED)
    sampled = set()
    while len(sampled) < 96:
        combo = (
            rng.choice([2.55, 2.60, 2.65, 2.70, 2.75, 2.80]),  # BASE_QUOTE_EDGE
            rng.choice([1.15, 1.20, 1.25, 1.30]),  # BASE_TAKE_EDGE
            rng.choice([0.76, 0.84, 0.92, 1.00]),  # SPREAD_VOL_COEF
            rng.choice([0.34, 0.38, 0.42, 0.46]),  # SPREAD_INV_COEF
            rng.choice([0.74, 0.82, 0.90, 0.98]),  # SPREAD_TIME_COEF
            rng.choice([1.04, 1.06, 1.08, 1.10]),  # ALPHA_EDGE_SCALE
            rng.choice([1.12, 1.16, 1.20, 1.24]),  # ALPHA_IMBALANCE_SCALE
            rng.choice([1.00, 1.03, 1.06]),  # ALPHA_THRESHOLD_SCALE
            rng.choice([0.10, 0.12, 0.14, 0.16]),  # RESERVATION_SCALE
            rng.choice([0.02, 0.04, 0.06]),  # TREND_RESERVATION_BIAS
            rng.choice([0.16, 0.20, 0.24]),  # RANGE_RESERVATION_BIAS
            rng.choice([0.20, 0.24, 0.28, 0.32]),  # TREND_SELL_HOLD_EXTRA
            rng.choice([0.04, 0.08, 0.12]),  # TREND_BUY_TAKE_EXTRA
            rng.choice([0.0, 1.0, 2.0]),  # TREND_QUOTE_LIFT_EXTRA
            rng.choice([0.04, 0.08, 0.12]),  # HOLD_TIME_COEF
        )
        sampled.add(combo)

    for index, combo in enumerate(sorted(sampled), start=1):
        (
            base_quote_edge,
            base_take_edge,
            spread_vol_coef,
            spread_inv_coef,
            spread_time_coef,
            alpha_edge_scale,
            alpha_imbalance_scale,
            alpha_threshold_scale,
            reservation_scale,
            trend_reservation_bias,
            range_reservation_bias,
            trend_sell_hold_extra,
            trend_buy_take_extra,
            trend_quote_lift_extra,
            hold_time_coef,
        ) = combo
        cases.append(
            make_case(
                base,
                f"plateau_random_{index:03d}",
                "random",
                {
                    "BASE_QUOTE_EDGE": base_quote_edge,
                    "BASE_TAKE_EDGE": base_take_edge,
                    "SPREAD_VOL_COEF": spread_vol_coef,
                    "SPREAD_INV_COEF": spread_inv_coef,
                    "SPREAD_TIME_COEF": spread_time_coef,
                    "ALPHA_EDGE_SCALE": alpha_edge_scale,
                    "ALPHA_IMBALANCE_SCALE": alpha_imbalance_scale,
                    "ALPHA_THRESHOLD_SCALE": alpha_threshold_scale,
                    "RESERVATION_SCALE": reservation_scale,
                    "TREND_RESERVATION_BIAS": trend_reservation_bias,
                    "RANGE_RESERVATION_BIAS": range_reservation_bias,
                    "TREND_SELL_HOLD_EXTRA": trend_sell_hold_extra,
                    "TREND_BUY_TAKE_EXTRA": trend_buy_take_extra,
                    "TREND_QUOTE_LIFT_EXTRA": trend_quote_lift_extra,
                    "HOLD_TIME_COEF": hold_time_coef,
                },
            )
        )

    return cases


def run_backtest(run_id: str, overrides: Dict[str, Dict[str, float]], label: str, family: str) -> Dict[str, object]:
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

    subprocess.run(
        command,
        cwd=WORKSPACE_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    metrics = json.loads((run_dir / "metrics.json").read_text())
    final_by_product = metrics.get("final_pnl_by_product", {})
    return {
        "label": label,
        "family": family,
        "run_id": run_id,
        "total_pnl": metrics.get("final_pnl_total", 0.0),
        "emeralds_pnl": final_by_product.get("EMERALDS", 0.0),
        "tomatoes_pnl": final_by_product.get("TOMATOES", 0.0),
        "own_trade_count": metrics.get("own_trade_count", 0),
        "overrides": overrides["TOMATOES"],
    }


def write_outputs(results: List[Dict[str, object]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with CSV_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "label",
                "family",
                "total_pnl",
                "emeralds_pnl",
                "tomatoes_pnl",
                "own_trade_count",
                "overrides_json",
            ]
        )
        for row in results:
            writer.writerow(
                [
                    row["label"],
                    row["family"],
                    row["total_pnl"],
                    row["emeralds_pnl"],
                    row["tomatoes_pnl"],
                    row["own_trade_count"],
                    json.dumps(row["overrides"], sort_keys=True),
                ]
            )

    baseline = next(row for row in results if row["label"] == "baseline_v29_1a")
    best = max(results, key=lambda row: row["total_pnl"])
    by_family: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in results:
        by_family[str(row["family"])].append(row)

    lines = [
        "V29.1a Plateau Sweep",
        f"Cases: {len(results)}",
        f"Baseline: {baseline['total_pnl']:.0f} total | TOMATOES {baseline['tomatoes_pnl']:.0f} | trades {baseline['own_trade_count']}",
        f"Best: {best['label']} | {best['total_pnl']:.0f} total | TOMATOES {best['tomatoes_pnl']:.0f} | trades {best['own_trade_count']}",
        "",
        "Top 10:",
    ]
    for row in sorted(results, key=lambda item: item["total_pnl"], reverse=True)[:10]:
        lines.append(
            f"- {row['label']}: total {row['total_pnl']:.0f} | TOMATOES {row['tomatoes_pnl']:.0f} | trades {row['own_trade_count']}"
        )

    lines.append("")
    lines.append("Best By Family:")
    for family, rows in sorted(by_family.items()):
        top = max(rows, key=lambda item: item["total_pnl"])
        lines.append(
            f"- {family}: {top['label']} | total {top['total_pnl']:.0f} | TOMATOES {top['tomatoes_pnl']:.0f}"
        )

    lines.append("")
    lines.append("Winning Overrides:")
    for key, value in sorted(best["overrides"].items()):
        if BASE_TOMATOES.get(key) != value:
            lines.append(f"- {key} = {value}")

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    defaults = load_defaults()
    cases = build_cases(defaults)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, object]] = []
    for index, case in enumerate(cases, start=1):
        run_id = f"v29-1a-plateau-{index:03d}"
        results.append(
            run_backtest(
                run_id,
                case["overrides"],
                str(case["label"]),
                str(case["family"]),
            )
        )

    results.sort(key=lambda row: row["total_pnl"], reverse=True)
    write_outputs(results)


if __name__ == "__main__":
    main()
