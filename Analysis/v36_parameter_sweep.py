#!/usr/bin/env python3

from __future__ import annotations

import csv
import itertools
import json
import random
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_TRADER = WORKSPACE_ROOT / "Bots" / "Traderv36.py"
GENERATED_TRADER = WORKSPACE_ROOT / "Bots" / "Traderv36_sweep_local.py"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v36_sweep_runs"
REPORT_PATH = OUTPUT_DIR / "v36_sweep_report.txt"
CSV_PATH = OUTPUT_DIR / "v36_sweep_results.csv"
RANDOM_SEED = 3601

BASE_PARAMS = {
    "BASE_QUOTE_EDGE": 2.30,
    "BASE_TAKE_EDGE": 1.00,
    "CENTER_ALPHA_WEIGHT": 0.34,
    "REVERSION_ALPHA_WEIGHT": 0.24,
    "TAKER_BUCKET_EDGE_WEIGHT": 0.20,
    "TARGET_BUCKET_WEIGHT": 0.10,
    "PASSIVE_BUCKET_EDGE_WEIGHT": 0.08,
    "PASSIVE_BUCKET_MARKOUT_WEIGHT": 0.06,
    "SPREAD_TOXIC_COEF": 0.78,
    "SOFT_LIMIT_BASE": 0.50,
    "SOFT_LIMIT_TREND_BONUS": 0.14,
    "SOFT_LIMIT_TOXIC_PENALTY": 0.14,
}


def clone_params(params: Dict[str, float]) -> Dict[str, float]:
    return dict(params)


def write_trader(params: Dict[str, float]) -> None:
    content = SOURCE_TRADER.read_text()
    for key, value in params.items():
        content, count = re.subn(
            rf'("{re.escape(key)}":\s*)([^,\n]+)(,)',
            rf"\g<1>{repr(value)}\g<3>",
            content,
            count=1,
        )
        if count != 1:
            raise RuntimeError(f"Failed to replace parameter {key}")
    GENERATED_TRADER.write_text(content)


def run_backtest(run_id: str, label: str, params: Dict[str, float]) -> Dict[str, object]:
    write_trader(params)
    run_dir = RUN_OUTPUT_ROOT / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)

    command = [
        str(BACKTESTER),
        "--trader",
        str(GENERATED_TRADER),
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
        cwd=WORKSPACE_ROOT / "ProsperityRustBacktester",
        capture_output=True,
        text=True,
        check=True,
    )

    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        raise RuntimeError(
            f"Missing metrics for {run_id}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    metrics = json.loads(metrics_path.read_text())
    by_product = metrics.get("final_pnl_by_product", {})
    return {
        "label": label,
        "run_id": run_id,
        "total": float(metrics["final_pnl_total"]),
        "emeralds": float(by_product.get("EMERALDS", 0.0)),
        "tomatoes": float(by_product.get("TOMATOES", 0.0)),
        "trades": int(metrics.get("own_trade_count", 0)),
        "params": clone_params(params),
    }


def build_cases() -> List[Dict[str, object]]:
    cases: List[Dict[str, object]] = [
        {"label": "baseline_v36", "params": clone_params(BASE_PARAMS)},
        {
            "label": "quote_wider_taker_lighter",
            "params": {
                **clone_params(BASE_PARAMS),
                "BASE_QUOTE_EDGE": 2.40,
                "BASE_TAKE_EDGE": 0.95,
                "CENTER_ALPHA_WEIGHT": 0.36,
                "TAKER_BUCKET_EDGE_WEIGHT": 0.16,
            },
        },
        {
            "label": "quote_tighter_taker_heavier",
            "params": {
                **clone_params(BASE_PARAMS),
                "BASE_QUOTE_EDGE": 2.20,
                "BASE_TAKE_EDGE": 1.05,
                "CENTER_ALPHA_WEIGHT": 0.32,
                "SPREAD_TOXIC_COEF": 0.86,
            },
        },
        {
            "label": "target_richer",
            "params": {
                **clone_params(BASE_PARAMS),
                "TARGET_BUCKET_WEIGHT": 0.14,
                "SOFT_LIMIT_BASE": 0.54,
                "SOFT_LIMIT_TREND_BONUS": 0.16,
                "SOFT_LIMIT_TOXIC_PENALTY": 0.12,
            },
        },
        {
            "label": "passive_overlay_lighter",
            "params": {
                **clone_params(BASE_PARAMS),
                "PASSIVE_BUCKET_EDGE_WEIGHT": 0.04,
                "PASSIVE_BUCKET_MARKOUT_WEIGHT": 0.03,
                "BASE_QUOTE_EDGE": 2.35,
            },
        },
        {
            "label": "passive_overlay_stronger",
            "params": {
                **clone_params(BASE_PARAMS),
                "PASSIVE_BUCKET_EDGE_WEIGHT": 0.10,
                "PASSIVE_BUCKET_MARKOUT_WEIGHT": 0.08,
                "BASE_QUOTE_EDGE": 2.35,
            },
        },
    ]

    rng = random.Random(RANDOM_SEED)
    sampled = set()
    grid = list(
        itertools.product(
            [2.20, 2.30, 2.40],   # BASE_QUOTE_EDGE
            [0.95, 1.00, 1.05],   # BASE_TAKE_EDGE
            [0.32, 0.34, 0.36],   # CENTER_ALPHA_WEIGHT
            [0.20, 0.24, 0.28],   # REVERSION_ALPHA_WEIGHT
            [0.14, 0.20, 0.26],   # TAKER_BUCKET_EDGE_WEIGHT
            [0.06, 0.10, 0.14],   # TARGET_BUCKET_WEIGHT
            [0.04, 0.08, 0.12],   # PASSIVE_BUCKET_EDGE_WEIGHT
            [0.03, 0.06, 0.09],   # PASSIVE_BUCKET_MARKOUT_WEIGHT
            [0.70, 0.78, 0.86],   # SPREAD_TOXIC_COEF
            [0.46, 0.50, 0.54],   # SOFT_LIMIT_BASE
            [0.12, 0.14, 0.16],   # SOFT_LIMIT_TREND_BONUS
            [0.12, 0.14, 0.16],   # SOFT_LIMIT_TOXIC_PENALTY
        )
    )
    while len(sampled) < 36:
        sampled.add(rng.choice(grid))

    for index, combo in enumerate(sorted(sampled), start=1):
        (
            base_quote_edge,
            base_take_edge,
            center_alpha_weight,
            reversion_alpha_weight,
            taker_bucket_edge_weight,
            target_bucket_weight,
            passive_bucket_edge_weight,
            passive_bucket_markout_weight,
            spread_toxic_coef,
            soft_limit_base,
            soft_limit_trend_bonus,
            soft_limit_toxic_penalty,
        ) = combo
        cases.append(
            {
                "label": f"v36_rand_{index:02d}",
                "params": {
                    "BASE_QUOTE_EDGE": base_quote_edge,
                    "BASE_TAKE_EDGE": base_take_edge,
                    "CENTER_ALPHA_WEIGHT": center_alpha_weight,
                    "REVERSION_ALPHA_WEIGHT": reversion_alpha_weight,
                    "TAKER_BUCKET_EDGE_WEIGHT": taker_bucket_edge_weight,
                    "TARGET_BUCKET_WEIGHT": target_bucket_weight,
                    "PASSIVE_BUCKET_EDGE_WEIGHT": passive_bucket_edge_weight,
                    "PASSIVE_BUCKET_MARKOUT_WEIGHT": passive_bucket_markout_weight,
                    "SPREAD_TOXIC_COEF": spread_toxic_coef,
                    "SOFT_LIMIT_BASE": soft_limit_base,
                    "SOFT_LIMIT_TREND_BONUS": soft_limit_trend_bonus,
                    "SOFT_LIMIT_TOXIC_PENALTY": soft_limit_toxic_penalty,
                },
            }
        )

    return cases


def write_outputs(results: List[Dict[str, object]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    with CSV_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["label", "run_id", "total", "emeralds", "tomatoes", "trades", "params_json"])
        for row in sorted(results, key=lambda item: item["total"], reverse=True):
            writer.writerow(
                [
                    row["label"],
                    row["run_id"],
                    row["total"],
                    row["emeralds"],
                    row["tomatoes"],
                    row["trades"],
                    json.dumps(row["params"], sort_keys=True),
                ]
            )

    ranked = sorted(results, key=lambda item: item["total"], reverse=True)
    baseline = next(row for row in results if row["label"] == "baseline_v36")
    lines = [
        "V36 focused local sweep",
        "",
        f"Baseline v36 Rust PnL: {baseline['total']:.0f} | EMERALDS {baseline['emeralds']:.0f} | TOMATOES {baseline['tomatoes']:.0f} | trades {baseline['trades']}",
        "",
        "Top results:",
    ]
    for row in ranked[:10]:
        delta = row["total"] - baseline["total"]
        lines.append(
            f"- {row['label']}: {row['total']:.0f} (delta {delta:+.0f}, TOMATOES {row['tomatoes']:.0f}, trades {row['trades']})"
        )
        lines.append(f"  params: {json.dumps(row['params'], sort_keys=True)}")

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    cases = build_cases()
    results: List[Dict[str, object]] = []
    for index, case in enumerate(cases):
        run_id = f"v36-sweep-{index:03d}"
        results.append(run_backtest(run_id, case["label"], case["params"]))
        print(
            f"[{index + 1}/{len(cases)}] {case['label']}: "
            f"{results[-1]['total']:.0f} total | TOMATOES {results[-1]['tomatoes']:.0f}"
        )

    write_outputs(results)


if __name__ == "__main__":
    main()
