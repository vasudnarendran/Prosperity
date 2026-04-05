#!/usr/bin/env python3

from __future__ import annotations

import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
TRADER_PATH = WORKSPACE_ROOT / "Bots" / "Traderv27_local.py"
BOT_DIR = WORKSPACE_ROOT / "Bots"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v27_alpha_hold_runs"
REPORT_PATH = OUTPUT_DIR / "v27_alpha_hold_report.txt"
CSV_PATH = OUTPUT_DIR / "v27_alpha_hold_results.csv"
ENV_NAME = "TRADER_PARAM_OVERRIDES"


def load_defaults() -> Dict[str, Dict[str, float]]:
    sys.path.insert(0, str(BOT_DIR))
    spec = importlib.util.spec_from_file_location("traderv27_local_alpha_hold_module", TRADER_PATH)
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


def make_case(
    base: Dict[str, Dict[str, float]],
    label: str,
    area: str,
    updates: Dict[str, float],
) -> Dict[str, object]:
    overrides = clone_overrides(base)
    overrides.setdefault("TOMATOES", {}).update(updates)
    return {"label": label, "area": area, "overrides": overrides}


def build_cases(defaults: Dict[str, Dict[str, float]]) -> List[Dict[str, object]]:
    base = clone_overrides(defaults)
    return [
        {"label": "baseline_v27", "area": "baseline", "overrides": base},
        make_case(
            base,
            "alpha_light",
            "alpha",
            {
                "ALPHA_EDGE_SCALE": 1.06,
                "ALPHA_IMBALANCE_SCALE": 1.08,
                "ALPHA_THRESHOLD_SCALE": 0.95,
            },
        ),
        make_case(
            base,
            "alpha_strong",
            "alpha",
            {
                "ALPHA_EDGE_SCALE": 1.14,
                "ALPHA_IMBALANCE_SCALE": 1.15,
                "ALPHA_THRESHOLD_SCALE": 0.90,
            },
        ),
        make_case(
            base,
            "alpha_defensive",
            "alpha",
            {
                "ALPHA_EDGE_SCALE": 0.92,
                "ALPHA_IMBALANCE_SCALE": 0.95,
                "ALPHA_THRESHOLD_SCALE": 1.08,
            },
        ),
        make_case(
            base,
            "hold_dynamic_light",
            "hold_limit",
            {
                "SOFT_LIMIT_BASE_RATIO": 0.58,
                "SOFT_LIMIT_TREND_BONUS": 0.10,
                "SOFT_LIMIT_VOL_PENALTY": 0.08,
                "SOFT_LIMIT_FIT_BONUS": 0.03,
            },
        ),
        make_case(
            base,
            "hold_dynamic_strong",
            "hold_limit",
            {
                "SOFT_LIMIT_BASE_RATIO": 0.52,
                "SOFT_LIMIT_TREND_BONUS": 0.18,
                "SOFT_LIMIT_VOL_PENALTY": 0.12,
                "SOFT_LIMIT_FIT_BONUS": 0.05,
            },
        ),
        make_case(
            base,
            "hold_dynamic_wide",
            "hold_limit",
            {
                "SOFT_LIMIT_BASE_RATIO": 0.66,
                "SOFT_LIMIT_TREND_BONUS": 0.14,
                "SOFT_LIMIT_VOL_PENALTY": 0.06,
                "SOFT_LIMIT_FIT_BONUS": 0.04,
            },
        ),
        make_case(
            base,
            "alpha_light_hold_light",
            "combo",
            {
                "ALPHA_EDGE_SCALE": 1.06,
                "ALPHA_IMBALANCE_SCALE": 1.08,
                "ALPHA_THRESHOLD_SCALE": 0.95,
                "SOFT_LIMIT_BASE_RATIO": 0.58,
                "SOFT_LIMIT_TREND_BONUS": 0.10,
                "SOFT_LIMIT_VOL_PENALTY": 0.08,
                "SOFT_LIMIT_FIT_BONUS": 0.03,
            },
        ),
        make_case(
            base,
            "alpha_strong_hold_strong",
            "combo",
            {
                "ALPHA_EDGE_SCALE": 1.14,
                "ALPHA_IMBALANCE_SCALE": 1.15,
                "ALPHA_THRESHOLD_SCALE": 0.90,
                "SOFT_LIMIT_BASE_RATIO": 0.52,
                "SOFT_LIMIT_TREND_BONUS": 0.18,
                "SOFT_LIMIT_VOL_PENALTY": 0.12,
                "SOFT_LIMIT_FIT_BONUS": 0.05,
            },
        ),
        make_case(
            base,
            "alpha_defensive_hold_wide",
            "combo",
            {
                "ALPHA_EDGE_SCALE": 0.92,
                "ALPHA_IMBALANCE_SCALE": 0.95,
                "ALPHA_THRESHOLD_SCALE": 1.08,
                "SOFT_LIMIT_BASE_RATIO": 0.66,
                "SOFT_LIMIT_TREND_BONUS": 0.14,
                "SOFT_LIMIT_VOL_PENALTY": 0.06,
                "SOFT_LIMIT_FIT_BONUS": 0.04,
            },
        ),
    ]


def run_backtest(run_id: str, overrides: Dict[str, Dict[str, float]], label: str, area: str) -> Dict[str, object]:
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
        "area": area,
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
        writer.writerow(["label", "area", "total", "emeralds", "tomatoes", "trade_count"])
        for row in results:
            writer.writerow([
                row["label"],
                row["area"],
                f"{row['total']:.2f}",
                f"{row['emeralds']:.2f}",
                f"{row['tomatoes']:.2f}",
                row["trade_count"],
            ])


def write_report(results: List[Dict[str, object]]) -> None:
    baseline = next(row for row in results if row["label"] == "baseline_v27")
    by_area: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in results:
        by_area[str(row["area"])].append(row)

    ranked = sorted(results, key=lambda row: row["total"], reverse=True)
    lines: List[str] = []
    lines.append("V27 alpha and dynamic holding-limit sweep\n")
    lines.append(
        f"Baseline v27 Rust PnL: {baseline['total']:.0f} | "
        f"EMERALDS {baseline['emeralds']:.0f} | TOMATOES {baseline['tomatoes']:.0f} | "
        f"trades {baseline['trade_count']}\n"
    )
    lines.append("Top results:")
    for row in ranked[:6]:
        delta = row["total"] - baseline["total"]
        lines.append(
            f"- {row['label']}: {row['total']:.0f} "
            f"(delta {delta:+.0f}, TOMATOES {row['tomatoes']:.0f}, trades {row['trade_count']})"
        )

    lines.append("")
    lines.append("Area summary:")
    for area in ["alpha", "hold_limit", "combo"]:
        area_rows = sorted(by_area[area], key=lambda row: row["total"], reverse=True)
        best = area_rows[0]
        avg = sum(row["total"] for row in area_rows) / len(area_rows)
        lines.append(
            f"- {area}: best {best['label']} at {best['total']:.0f}, "
            f"average {avg:.0f}, best delta {best['total'] - baseline['total']:+.0f}"
        )

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    defaults = load_defaults()
    cases = build_cases(defaults)
    results: List[Dict[str, object]] = []

    for index, case in enumerate(cases, start=1):
        run_id = f"v27-ah-{index:02d}"
        results.append(run_backtest(run_id, case["overrides"], case["label"], case["area"]))

    write_csv(results)
    write_report(results)

    baseline = next(row for row in results if row["label"] == "baseline_v27")
    best = max(results, key=lambda row: row["total"])
    print(
        f"Baseline: {baseline['total']:.0f} | "
        f"Best: {best['label']} {best['total']:.0f} "
        f"(delta {best['total'] - baseline['total']:+.0f})"
    )


if __name__ == "__main__":
    main()
