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
SOURCE_TRADER = WORKSPACE_ROOT / "Bots" / "Traderv39.py"
GENERATED_TRADER = WORKSPACE_ROOT / "Bots" / "Traderv39_sweep_local.py"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v39_sweep_runs"
REPORT_PATH = OUTPUT_DIR / "v39_sweep_report.txt"
CSV_PATH = OUTPUT_DIR / "v39_sweep_results.csv"
BEST_JSON_PATH = OUTPUT_DIR / "v39_sweep_best.json"
RANDOM_SEED = 3901

BASE_PARAMS = {
    "BASE_TAKE_EDGE": 0.80,
    "BASE_QUOTE_EDGE": 2.75,
    "ALPHA_EDGE_SCALE": 1.4153631,
    "RANGE_RESERVATION_BIAS": 0.26486122,
    "ALPHA_BLEND_WEIGHT": 0.22,
    "FAIR_ALPHA_WEIGHT": 0.35,
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
        {"label": "baseline_v39", "params": clone_params(BASE_PARAMS)},
        {
            "label": "safer_alpha_lighter",
            "params": {
                **clone_params(BASE_PARAMS),
                "BASE_TAKE_EDGE": 0.86,
                "BASE_QUOTE_EDGE": 2.90,
                "ALPHA_BLEND_WEIGHT": 0.16,
                "FAIR_ALPHA_WEIGHT": 0.24,
            },
        },
        {
            "label": "alpha_richer_quote_tighter",
            "params": {
                **clone_params(BASE_PARAMS),
                "BASE_TAKE_EDGE": 0.78,
                "BASE_QUOTE_EDGE": 2.68,
                "ALPHA_BLEND_WEIGHT": 0.28,
                "FAIR_ALPHA_WEIGHT": 0.42,
            },
        },
    ]

    rng = random.Random(RANDOM_SEED)
    grid = list(
        itertools.product(
            [0.78, 0.82, 0.86],         # BASE_TAKE_EDGE
            [2.68, 2.82, 2.96],         # BASE_QUOTE_EDGE
            [1.34, 1.42, 1.50],         # ALPHA_EDGE_SCALE
            [0.22, 0.27, 0.32],         # RANGE_RESERVATION_BIAS
            [0.10, 0.16, 0.22, 0.28],   # ALPHA_BLEND_WEIGHT
            [0.18, 0.24, 0.30, 0.36],   # FAIR_ALPHA_WEIGHT
        )
    )

    sampled = set()
    while len(sampled) < 48:
        sampled.add(rng.choice(grid))

    for index, combo in enumerate(sorted(sampled), start=1):
        (
            base_take_edge,
            base_quote_edge,
            alpha_edge_scale,
            range_reservation_bias,
            alpha_blend_weight,
            fair_alpha_weight,
        ) = combo
        cases.append(
            {
                "label": f"v39_rand_{index:02d}",
                "params": {
                    "BASE_TAKE_EDGE": base_take_edge,
                    "BASE_QUOTE_EDGE": base_quote_edge,
                    "ALPHA_EDGE_SCALE": alpha_edge_scale,
                    "RANGE_RESERVATION_BIAS": range_reservation_bias,
                    "ALPHA_BLEND_WEIGHT": alpha_blend_weight,
                    "FAIR_ALPHA_WEIGHT": fair_alpha_weight,
                },
            }
        )

    return cases


def write_outputs(results: List[Dict[str, object]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    ranked = sorted(results, key=lambda item: item["total"], reverse=True)
    baseline = next(row for row in results if row["label"] == "baseline_v39")
    best = ranked[0]

    with CSV_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["label", "run_id", "total", "emeralds", "tomatoes", "trades", "params_json"])
        for row in ranked:
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

    BEST_JSON_PATH.write_text(json.dumps(best, indent=2))

    lines = [
        "V39 focused local sweep",
        "",
        f"Baseline v39 Rust PnL: {baseline['total']:.0f} | EMERALDS {baseline['emeralds']:.0f} | TOMATOES {baseline['tomatoes']:.0f} | trades {baseline['trades']}",
        f"Best result: {best['label']} -> {best['total']:.0f} | EMERALDS {best['emeralds']:.0f} | TOMATOES {best['tomatoes']:.0f} | trades {best['trades']}",
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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    for index, case in enumerate(cases, start=1):
        run_id = f"v39-sweep-{index:02d}"
        results.append(run_backtest(run_id, str(case["label"]), case["params"]))

    write_outputs(results)

    best = max(results, key=lambda item: item["total"])
    print(f"baseline: {next(row for row in results if row['label'] == 'baseline_v39')['total']:.0f}")
    print(f"best: {best['label']} -> {best['total']:.0f}")
    print(f"report: {REPORT_PATH}")
    print(f"results: {CSV_PATH}")
    print(f"best_json: {BEST_JSON_PATH}")


if __name__ == "__main__":
    main()
