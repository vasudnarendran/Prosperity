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
TRADER_PATH = WORKSPACE_ROOT / "Bots" / "Traderv27_1_local.py"
BOT_DIR = WORKSPACE_ROOT / "Bots"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v27_2_region_runs"
REPORT_PATH = OUTPUT_DIR / "v27_2_region_report.txt"
CSV_PATH = OUTPUT_DIR / "v27_2_region_results.csv"
ENV_NAME = "TRADER_PARAM_OVERRIDES"
RANDOM_SEED = 272

BASE_TOMATOES = {
    "ALPHA_EDGE_SCALE": 1.04,
    "ALPHA_IMBALANCE_SCALE": 1.12,
    "ALPHA_THRESHOLD_SCALE": 1.00,
    "BASE_QUOTE_EDGE": 2.40,
    "BASE_TAKE_EDGE": 1.20,
    "GAMMA_RANGE": 0.28,
    "GAMMA_TREND": 0.14,
    "GAMMA_VOLATILE": 0.24,
    "HOLD_TIME_COEF": 0.0,
    "HOLD_VOL_COEF": 0.0,
    "RANGE_RESERVATION_BIAS": 0.16,
    "RESERVATION_SCALE": 0.16,
    "SPREAD_INV_COEF": 0.24,
    "SPREAD_TIME_COEF": 0.64,
    "SPREAD_VOL_COEF": 0.56,
    "TREND_BUY_TAKE_EXTRA": 0.12,
    "TREND_QUOTE_LIFT_EXTRA": 0.0,
    "TREND_RESERVATION_BIAS": 0.08,
    "TREND_SELL_HOLD_EXTRA": 0.16,
}


def load_defaults() -> Dict[str, Dict[str, float]]:
    sys.path.insert(0, str(BOT_DIR))
    spec = importlib.util.spec_from_file_location("traderv27_2_region_module", TRADER_PATH)
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
        {"label": "baseline_v27_2_region", "family": "baseline", "overrides": base},
        make_case(
            base,
            "spread_heavy_plus",
            "designed",
            {
                "SPREAD_VOL_COEF": 0.64,
                "SPREAD_INV_COEF": 0.28,
                "SPREAD_TIME_COEF": 0.72,
                "BASE_QUOTE_EDGE": 2.50,
            },
        ),
        make_case(
            base,
            "reservation_heavy_plus",
            "designed",
            {
                "GAMMA_RANGE": 0.34,
                "GAMMA_TREND": 0.18,
                "GAMMA_VOLATILE": 0.32,
                "RESERVATION_SCALE": 0.20,
                "TREND_RESERVATION_BIAS": 0.04,
                "RANGE_RESERVATION_BIAS": 0.20,
            },
        ),
        make_case(
            base,
            "sell_patience_plus",
            "designed",
            {
                "TREND_SELL_HOLD_EXTRA": 0.24,
                "TREND_BUY_TAKE_EXTRA": 0.16,
                "HOLD_TIME_COEF": 0.08,
            },
        ),
        make_case(
            base,
            "alpha_plus",
            "designed",
            {
                "ALPHA_EDGE_SCALE": 1.06,
                "ALPHA_IMBALANCE_SCALE": 1.16,
                "ALPHA_THRESHOLD_SCALE": 0.95,
            },
        ),
        make_case(
            base,
            "spread_reservation_mix",
            "designed",
            {
                "SPREAD_VOL_COEF": 0.64,
                "SPREAD_INV_COEF": 0.28,
                "SPREAD_TIME_COEF": 0.72,
                "RESERVATION_SCALE": 0.20,
                "TREND_RESERVATION_BIAS": 0.04,
                "RANGE_RESERVATION_BIAS": 0.20,
            },
        ),
        make_case(
            base,
            "spread_sell_mix",
            "designed",
            {
                "SPREAD_VOL_COEF": 0.64,
                "SPREAD_INV_COEF": 0.28,
                "SPREAD_TIME_COEF": 0.72,
                "TREND_SELL_HOLD_EXTRA": 0.20,
                "TREND_BUY_TAKE_EXTRA": 0.16,
                "BASE_TAKE_EDGE": 1.25,
            },
        ),
        make_case(
            base,
            "reservation_sell_mix",
            "designed",
            {
                "GAMMA_RANGE": 0.34,
                "GAMMA_TREND": 0.18,
                "GAMMA_VOLATILE": 0.32,
                "RESERVATION_SCALE": 0.20,
                "TREND_RESERVATION_BIAS": 0.04,
                "RANGE_RESERVATION_BIAS": 0.20,
                "TREND_SELL_HOLD_EXTRA": 0.20,
            },
        ),
        make_case(
            base,
            "balanced_push",
            "designed",
            {
                "ALPHA_IMBALANCE_SCALE": 1.16,
                "SPREAD_VOL_COEF": 0.64,
                "SPREAD_INV_COEF": 0.28,
                "SPREAD_TIME_COEF": 0.72,
                "BASE_TAKE_EDGE": 1.25,
                "BASE_QUOTE_EDGE": 2.50,
                "TREND_SELL_HOLD_EXTRA": 0.20,
            },
        ),
    ]

    rng = random.Random(RANDOM_SEED)
    sampled = set()
    while len(sampled) < 54:
        combo = (
            rng.choice([1.02, 1.04, 1.06]),  # ALPHA_EDGE_SCALE
            rng.choice([1.08, 1.12, 1.16]),  # ALPHA_IMBALANCE_SCALE
            rng.choice([0.95, 1.00, 1.03]),  # ALPHA_THRESHOLD_SCALE
            rng.choice([0.12, 0.16, 0.20]),  # RESERVATION_SCALE
            rng.choice([0.04, 0.08, 0.12]),  # TREND_RES_BIAS
            rng.choice([0.12, 0.16, 0.20]),  # RANGE_RES_BIAS
            rng.choice([0.48, 0.56, 0.64]),  # SPREAD_VOL_COEF
            rng.choice([0.20, 0.24, 0.28]),  # SPREAD_INV_COEF
            rng.choice([0.56, 0.64, 0.72]),  # SPREAD_TIME_COEF
            rng.choice([1.10, 1.20, 1.25]),  # BASE_TAKE_EDGE
            rng.choice([2.25, 2.40, 2.50]),  # BASE_QUOTE_EDGE
            rng.choice([0.08, 0.16, 0.24]),  # TREND_SELL_HOLD_EXTRA
            rng.choice([0.08, 0.12, 0.16]),  # TREND_BUY_TAKE_EXTRA
            rng.choice([0.0, 1.0]),          # TREND_QUOTE_LIFT_EXTRA
            rng.choice([0.0, 0.08]),         # HOLD_TIME_COEF
            rng.choice([0.0, 0.06]),         # HOLD_VOL_COEF
            rng.choice([0.22, 0.28, 0.34]),  # GAMMA_RANGE
            rng.choice([0.10, 0.14, 0.18]),  # GAMMA_TREND
            rng.choice([0.24, 0.32, 0.40]),  # GAMMA_VOLATILE
        )
        sampled.add(combo)

    for index, combo in enumerate(sorted(sampled), start=1):
        (
            alpha_edge_scale,
            alpha_imbalance_scale,
            alpha_threshold_scale,
            reservation_scale,
            trend_reservation_bias,
            range_reservation_bias,
            spread_vol_coef,
            spread_inv_coef,
            spread_time_coef,
            base_take_edge,
            base_quote_edge,
            trend_sell_hold_extra,
            trend_buy_take_extra,
            trend_quote_lift_extra,
            hold_time_coef,
            hold_vol_coef,
            gamma_range,
            gamma_trend,
            gamma_volatile,
        ) = combo
        cases.append(
            make_case(
                base,
                f"region_random_{index:02d}",
                "random",
                {
                    "ALPHA_EDGE_SCALE": alpha_edge_scale,
                    "ALPHA_IMBALANCE_SCALE": alpha_imbalance_scale,
                    "ALPHA_THRESHOLD_SCALE": alpha_threshold_scale,
                    "RESERVATION_SCALE": reservation_scale,
                    "TREND_RESERVATION_BIAS": trend_reservation_bias,
                    "RANGE_RESERVATION_BIAS": range_reservation_bias,
                    "SPREAD_VOL_COEF": spread_vol_coef,
                    "SPREAD_INV_COEF": spread_inv_coef,
                    "SPREAD_TIME_COEF": spread_time_coef,
                    "BASE_TAKE_EDGE": base_take_edge,
                    "BASE_QUOTE_EDGE": base_quote_edge,
                    "TREND_SELL_HOLD_EXTRA": trend_sell_hold_extra,
                    "TREND_BUY_TAKE_EXTRA": trend_buy_take_extra,
                    "TREND_QUOTE_LIFT_EXTRA": trend_quote_lift_extra,
                    "HOLD_TIME_COEF": hold_time_coef,
                    "HOLD_VOL_COEF": hold_vol_coef,
                    "GAMMA_RANGE": gamma_range,
                    "GAMMA_TREND": gamma_trend,
                    "GAMMA_VOLATILE": gamma_volatile,
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
    product_pnl = metrics["final_pnl_by_product"]
    total = float(metrics["final_pnl_total"])
    return {
        "label": label,
        "family": family,
        "total": total,
        "emeralds": float(product_pnl.get("EMERALDS", 0.0)),
        "tomatoes": float(product_pnl.get("TOMATOES", 0.0)),
        "trade_count": int(metrics.get("own_trade_count", 0)),
        "run_dir": str(run_dir.relative_to(WORKSPACE_ROOT)),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    defaults = load_defaults()
    cases = build_cases(defaults)
    results: List[Dict[str, object]] = []

    for index, case in enumerate(cases, start=1):
        result = run_backtest(
            run_id=f"v27-2-region-{index:03d}",
            overrides=case["overrides"],
            label=str(case["label"]),
            family=str(case["family"]),
        )
        results.append(result)

    baseline = next(result for result in results if result["label"] == "baseline_v27_2_region")
    for result in results:
        result["delta_vs_baseline"] = float(result["total"]) - float(baseline["total"])

    sorted_results = sorted(results, key=lambda item: float(item["total"]), reverse=True)

    with CSV_PATH.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["label", "family", "total", "emeralds", "tomatoes", "trade_count"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow({key: result[key] for key in writer.fieldnames})

    family_best: Dict[str, Dict[str, object]] = {}
    family_values: Dict[str, List[float]] = defaultdict(list)
    for result in results:
        family = str(result["family"])
        family_values[family].append(float(result["total"]))
        current_best = family_best.get(family)
        if current_best is None or float(result["total"]) > float(current_best["total"]):
            family_best[family] = result

    lines = [
        "V27.2 regional continuation sweep",
        "",
        (
            f"Baseline v27.2-region Rust PnL: {baseline['total']:.0f} | "
            f"EMERALDS {baseline['emeralds']:.0f} | TOMATOES {baseline['tomatoes']:.0f} | "
            f"trades {baseline['trade_count']}"
        ),
        "",
        "Top results:",
    ]

    for result in sorted_results[:10]:
        delta = float(result["delta_vs_baseline"])
        lines.append(
            f"- {result['label']}: {result['total']:.0f} "
            f"(delta {delta:+.0f}, TOMATOES {result['tomatoes']:.0f}, trades {result['trade_count']})"
        )

    lines.extend(["", "Family summary:"])
    for family, best in sorted(family_best.items()):
        average = sum(family_values[family]) / len(family_values[family])
        lines.append(
            f"- {family}: best {best['label']} at {best['total']:.0f}, "
            f"average {average:.0f}, best delta {float(best['delta_vs_baseline']):+.0f}"
        )

    best = sorted_results[0]
    lines.extend(
        [
            "",
            "Interpretation:",
            f"- Best overall case: {best['label']} ({best['family']}) at {best['total']:.0f}.",
            "- This sweep focuses on the stronger v27.2 neighborhood instead of the older v27.1 region.",
            "- It is designed to show whether spread control, reservation control, or sell-patience style changes are still the strongest local driver once combined with the v27.2 baseline.",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(
        f"Baseline: {baseline['total']:.0f} | Best: {best['label']} {best['total']:.0f} "
        f"(delta {float(best['delta_vs_baseline']):+.0f})"
    )


if __name__ == "__main__":
    main()
