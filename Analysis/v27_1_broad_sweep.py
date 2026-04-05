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
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v27_1_broad_runs"
REPORT_PATH = OUTPUT_DIR / "v27_1_broad_sweep_report.txt"
CSV_PATH = OUTPUT_DIR / "v27_1_broad_sweep_results.csv"
ENV_NAME = "TRADER_PARAM_OVERRIDES"
RANDOM_SEED = 271


def load_defaults() -> Dict[str, Dict[str, float]]:
    sys.path.insert(0, str(BOT_DIR))
    spec = importlib.util.spec_from_file_location("traderv27_1_local_sweep_module", TRADER_PATH)
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
    cases: List[Dict[str, object]] = [
        {"label": "baseline_v27_1", "family": "baseline", "overrides": base},
        make_case(
            base,
            "sell_patience",
            "designed",
            {
                "TREND_SELL_HOLD_EXTRA": 0.18,
                "TREND_QUOTE_LIFT_EXTRA": 1.0,
                "HOLD_TIME_COEF": 0.10,
            },
        ),
        make_case(
            base,
            "faster_trend_commit",
            "designed",
            {
                "ALPHA_EDGE_SCALE": 1.10,
                "ALPHA_THRESHOLD_SCALE": 0.92,
                "TREND_BUY_TAKE_EXTRA": 0.08,
            },
        ),
        make_case(
            base,
            "gamma_light",
            "designed",
            {
                "GAMMA_RANGE": 0.16,
                "GAMMA_TREND": 0.07,
                "GAMMA_VOLATILE": 0.24,
                "RESERVATION_SCALE": 0.08,
            },
        ),
        make_case(
            base,
            "gamma_heavy",
            "designed",
            {
                "GAMMA_RANGE": 0.28,
                "GAMMA_TREND": 0.14,
                "GAMMA_VOLATILE": 0.40,
                "RESERVATION_SCALE": 0.16,
            },
        ),
        make_case(
            base,
            "wide_mm",
            "designed",
            {
                "SPREAD_VOL_COEF": 0.52,
                "SPREAD_INV_COEF": 0.22,
                "SPREAD_TIME_COEF": 0.62,
                "BASE_QUOTE_EDGE": 2.40,
            },
        ),
        make_case(
            base,
            "tighter_mm",
            "designed",
            {
                "SPREAD_VOL_COEF": 0.30,
                "SPREAD_INV_COEF": 0.10,
                "SPREAD_TIME_COEF": 0.34,
                "BASE_QUOTE_EDGE": 2.10,
            },
        ),
        make_case(
            base,
            "alpha_spread_sell_hold",
            "designed",
            {
                "ALPHA_EDGE_SCALE": 1.10,
                "ALPHA_IMBALANCE_SCALE": 1.10,
                "ALPHA_THRESHOLD_SCALE": 0.92,
                "SPREAD_VOL_COEF": 0.48,
                "SPREAD_INV_COEF": 0.18,
                "SPREAD_TIME_COEF": 0.56,
                "TREND_SELL_HOLD_EXTRA": 0.15,
                "TREND_QUOTE_LIFT_EXTRA": 1.0,
            },
        ),
        make_case(
            base,
            "reservation_flip_light",
            "designed",
            {
                "RESERVATION_SCALE": 0.04,
                "TREND_RESERVATION_BIAS": 0.05,
                "RANGE_RESERVATION_BIAS": 0.02,
            },
        ),
    ]

    rng = random.Random(RANDOM_SEED)
    sampled = set()
    while len(sampled) < 48:
        combo = (
            rng.choice([1.00, 1.04, 1.06, 1.10, 1.14]),  # ALPHA_EDGE_SCALE
            rng.choice([1.00, 1.04, 1.08, 1.12]),        # ALPHA_IMBALANCE_SCALE
            rng.choice([0.88, 0.92, 0.95, 1.00]),        # ALPHA_THRESHOLD_SCALE
            rng.choice([0.08, 0.12, 0.16, 0.20]),        # RESERVATION_SCALE
            rng.choice([0.08, 0.14, 0.18, 0.24]),        # TREND_RESERVATION_BIAS
            rng.choice([0.04, 0.08, 0.12, 0.16]),        # RANGE_RESERVATION_BIAS
            rng.choice([0.32, 0.42, 0.48, 0.56]),        # SPREAD_VOL_COEF
            rng.choice([0.10, 0.16, 0.20, 0.24]),        # SPREAD_INV_COEF
            rng.choice([0.36, 0.50, 0.56, 0.64]),        # SPREAD_TIME_COEF
            rng.choice([1.10, 1.20, 1.30]),              # BASE_TAKE_EDGE
            rng.choice([2.10, 2.25, 2.40, 2.55]),        # BASE_QUOTE_EDGE
            rng.choice([0.00, 0.08, 0.16]),              # TREND_SELL_HOLD_EXTRA
            rng.choice([0.00, 1.00]),                    # TREND_QUOTE_LIFT_EXTRA
            rng.choice([0.00, 0.08, 0.12]),              # TREND_BUY_TAKE_EXTRA
            rng.choice([0.00, 0.08, 0.12]),              # HOLD_TIME_COEF
            rng.choice([0.00, 0.06, 0.10]),              # HOLD_VOL_COEF
            rng.choice([0.14, 0.18, 0.22, 0.28]),        # GAMMA_RANGE
            rng.choice([0.06, 0.10, 0.14]),              # GAMMA_TREND
            rng.choice([0.24, 0.32, 0.40]),              # GAMMA_VOLATILE
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
            trend_quote_lift_extra,
            trend_buy_take_extra,
            hold_time_coef,
            hold_vol_coef,
            gamma_range,
            gamma_trend,
            gamma_volatile,
        ) = combo
        cases.append(
            make_case(
                base,
                f"broad_random_{index:02d}",
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
                    "TREND_QUOTE_LIFT_EXTRA": trend_quote_lift_extra,
                    "TREND_BUY_TAKE_EXTRA": trend_buy_take_extra,
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
        "family": family,
        "total": float(metrics["final_pnl_total"]),
        "emeralds": float(by_product.get("EMERALDS", 0.0)),
        "tomatoes": float(by_product.get("TOMATOES", 0.0)),
        "trade_count": int(metrics.get("own_trade_count", 0)),
        "overrides": clone_overrides(overrides),
    }


def write_csv(results: List[Dict[str, object]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["label", "family", "total", "emeralds", "tomatoes", "trade_count"])
        for row in results:
            writer.writerow([
                row["label"],
                row["family"],
                f"{row['total']:.2f}",
                f"{row['emeralds']:.2f}",
                f"{row['tomatoes']:.2f}",
                row["trade_count"],
            ])


def write_report(results: List[Dict[str, object]]) -> None:
    baseline = next(row for row in results if row["label"] == "baseline_v27_1")
    ranked = sorted(results, key=lambda row: row["total"], reverse=True)
    by_family: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in results:
        by_family[str(row["family"])].append(row)

    lines: List[str] = []
    lines.append("V27.1 broad continuation sweep\n")
    lines.append(
        f"Baseline v27.1 Rust PnL: {baseline['total']:.0f} | "
        f"EMERALDS {baseline['emeralds']:.0f} | TOMATOES {baseline['tomatoes']:.0f} | "
        f"trades {baseline['trade_count']}\n"
    )
    lines.append("Top results:")
    for row in ranked[:10]:
        delta = row["total"] - baseline["total"]
        lines.append(
            f"- {row['label']}: {row['total']:.0f} "
            f"(delta {delta:+.0f}, TOMATOES {row['tomatoes']:.0f}, trades {row['trade_count']})"
        )

    lines.append("")
    lines.append("Family summary:")
    for family in ["designed", "random"]:
        if family not in by_family:
            continue
        fam_rows = sorted(by_family[family], key=lambda row: row["total"], reverse=True)
        best = fam_rows[0]
        avg = sum(row["total"] for row in fam_rows) / len(fam_rows)
        lines.append(
            f"- {family}: best {best['label']} at {best['total']:.0f}, "
            f"average {avg:.0f}, best delta {best['total'] - baseline['total']:+.0f}"
        )

    lines.append("")
    lines.append("Interpretation:")
    best_nonbaseline = next(row for row in ranked if row["label"] != "baseline_v27_1")
    lines.append(
        f"- Best overall non-baseline case: {best_nonbaseline['label']} "
        f"({best_nonbaseline['family']}) at {best_nonbaseline['total']:.0f}."
    )
    lines.append("- Designed cases test more abstract control styles such as sell patience, gamma changes, and maker-vs-taker balance.")
    lines.append("- Random cases search a wider nearby region across alpha scaling, reservation control, spread control, and asymmetric trend behavior.")

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    defaults = load_defaults()
    cases = build_cases(defaults)
    results: List[Dict[str, object]] = []

    for index, case in enumerate(cases, start=1):
        run_id = f"v27-1-broad-{index:03d}"
        results.append(run_backtest(run_id, case["overrides"], case["label"], case["family"]))

    write_csv(results)
    write_report(results)

    baseline = next(row for row in results if row["label"] == "baseline_v27_1")
    best = max(results, key=lambda row: row["total"])
    print(
        f"Baseline: {baseline['total']:.0f} | "
        f"Best: {best['label']} {best['total']:.0f} "
        f"(delta {best['total'] - baseline['total']:+.0f})"
    )


if __name__ == "__main__":
    main()
