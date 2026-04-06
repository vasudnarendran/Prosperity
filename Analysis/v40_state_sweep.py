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
SOURCE_TRADER = WORKSPACE_ROOT / "Bots" / "Traderv40_3.py"
GENERATED_TRADER = WORKSPACE_ROOT / "Bots" / "Traderv40_4_candidate.py"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v40_state_sweep_runs"
REPORT_PATH = OUTPUT_DIR / "v40_state_sweep_report.txt"
CSV_PATH = OUTPUT_DIR / "v40_state_sweep_results.csv"
BEST_JSON_PATH = OUTPUT_DIR / "v40_state_sweep_best.json"
RANDOM_SEED = 4003

BASE_PARAMS = {
    "CALM_JOIN_IMPROVEMENT": 2.0,
    "CALM_QUOTE_EDGE_MULT": 0.91,
    "FAST_QUOTE_EDGE_MULT": 1.02,
    "FAST_TAKE_EDGE_BONUS": 0.16,
    "FAST_TARGET_BONUS": 3.0,
    "INVENTORY_EDGE_PRESSURE": 0.42,
    "INVENTORY_SIZE_PRESSURE": 0.35,
    "GOOD_FILL_TAKE_BONUS": 0.08,
    "BAD_FILL_TAKE_PENALTY": 0.14,
    "BAD_FILL_QUOTE_PENALTY": 0.12,
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
        {"label": "baseline_v40_3", "params": clone_params(BASE_PARAMS)},
        {
            "label": "lighter_fast_widening",
            "params": {
                **clone_params(BASE_PARAMS),
                "FAST_QUOTE_EDGE_MULT": 1.00,
                "FAST_TAKE_EDGE_BONUS": 0.18,
                "BAD_FILL_TAKE_PENALTY": 0.10,
                "BAD_FILL_QUOTE_PENALTY": 0.08,
            },
        },
        {
            "label": "more_calm_joining",
            "params": {
                **clone_params(BASE_PARAMS),
                "CALM_JOIN_IMPROVEMENT": 3.0,
                "CALM_QUOTE_EDGE_MULT": 0.89,
                "INVENTORY_EDGE_PRESSURE": 0.35,
                "INVENTORY_SIZE_PRESSURE": 0.30,
            },
        },
        {
            "label": "feedback_lighter",
            "params": {
                **clone_params(BASE_PARAMS),
                "GOOD_FILL_TAKE_BONUS": 0.10,
                "BAD_FILL_TAKE_PENALTY": 0.08,
                "BAD_FILL_QUOTE_PENALTY": 0.06,
                "FAST_TARGET_BONUS": 2.0,
            },
        },
    ]

    rng = random.Random(RANDOM_SEED)
    grid = list(
        itertools.product(
            [1.0, 2.0, 3.0],            # CALM_JOIN_IMPROVEMENT
            [0.89, 0.91, 0.94],         # CALM_QUOTE_EDGE_MULT
            [1.00, 1.02, 1.05],         # FAST_QUOTE_EDGE_MULT
            [0.12, 0.16, 0.20],         # FAST_TAKE_EDGE_BONUS
            [2.0, 3.0, 4.0],            # FAST_TARGET_BONUS
            [0.30, 0.35, 0.42],         # INVENTORY_EDGE_PRESSURE
            [0.20, 0.30, 0.35],         # INVENTORY_SIZE_PRESSURE
            [0.04, 0.08, 0.12],         # GOOD_FILL_TAKE_BONUS
            [0.08, 0.14, 0.20],         # BAD_FILL_TAKE_PENALTY
            [0.06, 0.12, 0.18],         # BAD_FILL_QUOTE_PENALTY
        )
    )

    sampled = set()
    while len(sampled) < 40:
        sampled.add(rng.choice(grid))

    for index, combo in enumerate(sorted(sampled), start=1):
        (
            calm_join_improvement,
            calm_quote_edge_mult,
            fast_quote_edge_mult,
            fast_take_edge_bonus,
            fast_target_bonus,
            inventory_edge_pressure,
            inventory_size_pressure,
            good_fill_take_bonus,
            bad_fill_take_penalty,
            bad_fill_quote_penalty,
        ) = combo
        cases.append(
            {
                "label": f"v40_state_{index:02d}",
                "params": {
                    "CALM_JOIN_IMPROVEMENT": calm_join_improvement,
                    "CALM_QUOTE_EDGE_MULT": calm_quote_edge_mult,
                    "FAST_QUOTE_EDGE_MULT": fast_quote_edge_mult,
                    "FAST_TAKE_EDGE_BONUS": fast_take_edge_bonus,
                    "FAST_TARGET_BONUS": fast_target_bonus,
                    "INVENTORY_EDGE_PRESSURE": inventory_edge_pressure,
                    "INVENTORY_SIZE_PRESSURE": inventory_size_pressure,
                    "GOOD_FILL_TAKE_BONUS": good_fill_take_bonus,
                    "BAD_FILL_TAKE_PENALTY": bad_fill_take_penalty,
                    "BAD_FILL_QUOTE_PENALTY": bad_fill_quote_penalty,
                },
            }
        )

    return cases


def write_outputs(results: List[Dict[str, object]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    ranked = sorted(results, key=lambda item: item["total"], reverse=True)
    baseline = next(row for row in results if row["label"] == "baseline_v40_3")
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
        "V40 state-layer sweep",
        "",
        f"Baseline v40.3 Rust PnL: {baseline['total']:.0f} | EMERALDS {baseline['emeralds']:.0f} | TOMATOES {baseline['tomatoes']:.0f} | trades {baseline['trades']}",
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
        run_id = f"v40-state-sweep-{index:02d}"
        results.append(run_backtest(run_id, str(case["label"]), case["params"]))

    write_outputs(results)

    best = max(results, key=lambda item: item["total"])
    print(f"baseline: {next(row for row in results if row['label'] == 'baseline_v40_3')['total']:.0f}")
    print(f"best: {best['label']} -> {best['total']:.0f}")
    print(f"report: {REPORT_PATH}")
    print(f"results: {CSV_PATH}")
    print(f"best_json: {BEST_JSON_PATH}")


if __name__ == "__main__":
    main()
