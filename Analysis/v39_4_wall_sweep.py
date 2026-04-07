#!/usr/bin/env python3

from __future__ import annotations

import csv
import itertools
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_TRADER = WORKSPACE_ROOT / "Bots" / "Traderv39_4.py"
GENERATED_TRADER = WORKSPACE_ROOT / "Bots" / "Traderv39_4_sweep_local.py"
BACKTESTER_CWD = WORKSPACE_ROOT / "ProsperityRustBacktester"
TARGET_DIR = BACKTESTER_CWD / "target_local"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v39_4_wall_sweep_runs"
REPORT_PATH = OUTPUT_DIR / "v39_4_wall_sweep_report.txt"
CSV_PATH = OUTPUT_DIR / "v39_4_wall_sweep_results.csv"
BEST_JSON_PATH = OUTPUT_DIR / "v39_4_wall_sweep_best.json"

BASE_PARAMS = {
    "WALL_ALPHA_WEIGHT": 0.10,
    "WALL_FAIR_WEIGHT": 0.16,
    "WALL_EWMA_ALPHA": 0.22,
    "WALL_PERSISTENCE_FLOOR": 0.35,
}


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


def ensure_backtester_built() -> None:
    command = [
        "./scripts/cargo_local.sh",
        "build",
        "--release",
    ]
    subprocess.run(
        command,
        cwd=BACKTESTER_CWD,
        check=True,
        env={
            **dict(**subprocess.os.environ),
            "CARGO_TARGET_DIR": str(TARGET_DIR),
            "PYO3_PYTHON": "/opt/homebrew/bin/python3.12",
        },
        capture_output=True,
        text=True,
    )


def run_backtest(run_id: str, label: str, params: Dict[str, float]) -> Dict[str, object]:
    write_trader(params)
    run_dir = RUN_OUTPUT_ROOT / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)

    command = [
        str(TARGET_DIR / "release" / "rust_backtester"),
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
        cwd=BACKTESTER_CWD,
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
        "params": dict(params),
    }


def build_cases() -> List[Dict[str, object]]:
    cases: List[Dict[str, object]] = [{"label": "baseline_v39_4", "params": dict(BASE_PARAMS)}]
    grid = itertools.product(
        [0.00, 0.05, 0.10],
        [0.12, 0.16, 0.20],
        [0.16, 0.22, 0.30],
        [0.25, 0.35, 0.45],
    )
    for index, (alpha_w, fair_w, ewma_a, floor_v) in enumerate(grid, start=1):
        params = {
            "WALL_ALPHA_WEIGHT": alpha_w,
            "WALL_FAIR_WEIGHT": fair_w,
            "WALL_EWMA_ALPHA": ewma_a,
            "WALL_PERSISTENCE_FLOOR": floor_v,
        }
        label = f"wall_{index:02d}"
        cases.append({"label": label, "params": params})
    return cases


def write_outputs(results: List[Dict[str, object]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    ranked = sorted(results, key=lambda item: item["total"], reverse=True)
    baseline = next(row for row in results if row["label"] == "baseline_v39_4")
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
        "V39.4 wall-fair focused sweep",
        "",
        f"Baseline v39.4 Rust PnL: {baseline['total']:.0f} | EMERALDS {baseline['emeralds']:.0f} | TOMATOES {baseline['tomatoes']:.0f} | trades {baseline['trades']}",
        f"Best result: {best['label']} -> {best['total']:.0f} | EMERALDS {best['emeralds']:.0f} | TOMATOES {best['tomatoes']:.0f} | trades {best['trades']}",
        "",
        "Top results:",
    ]
    for row in ranked[:12]:
        delta = row["total"] - baseline["total"]
        lines.append(
            f"- {row['label']}: {row['total']:.0f} (delta {delta:+.0f}, TOMATOES {row['tomatoes']:.0f}, trades {row['trades']})"
        )
        lines.append(f"  params: {json.dumps(row['params'], sort_keys=True)}")

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    ensure_backtester_built()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    cases = build_cases()
    results: List[Dict[str, object]] = []
    for index, case in enumerate(cases, start=1):
        run_id = f"v39-4-wall-{index:02d}"
        results.append(run_backtest(run_id, str(case["label"]), case["params"]))

    write_outputs(results)

    baseline = next(row for row in results if row["label"] == "baseline_v39_4")
    best = max(results, key=lambda item: item["total"])
    print(f"baseline: {baseline['total']:.0f}")
    print(f"best: {best['label']} -> {best['total']:.0f}")
    print(f"report: {REPORT_PATH}")
    print(f"results: {CSV_PATH}")
    print(f"best_json: {BEST_JSON_PATH}")


if __name__ == "__main__":
    main()
