#!/usr/bin/env python3

from __future__ import annotations

import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
TRADER_PATH = WORKSPACE_ROOT / "Bots" / "Traderv17_local.py"
BOT_DIR = WORKSPACE_ROOT / "Bots"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v17_sweep_runs"
REPORT_PATH = OUTPUT_DIR / "v17_sweep_report.txt"
CSV_PATH = OUTPUT_DIR / "v17_sweep_results.csv"
ENV_NAME = "TRADER_PARAM_OVERRIDES"


@dataclass
class SweepLayer:
    label: str
    values: List[float]
    description: str
    apply: Callable[[Dict[str, Dict[str, float]], float], None]


def load_v17_defaults() -> Dict[str, Dict[str, float]]:
    sys.path.insert(0, str(BOT_DIR))
    spec = importlib.util.spec_from_file_location("traderv17_sweep_module", TRADER_PATH)
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


def set_value(overrides: Dict[str, Dict[str, float]], key: str, value: float) -> None:
    overrides.setdefault("TOMATOES", {})[key] = value


def format_value(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}"


def sanitize_run_component(value: str) -> str:
    return value.replace(".", "p").replace("-", "m").replace(" ", "-").lower()


def run_backtest(run_id: str, overrides: Dict[str, Dict[str, float]]) -> Dict[str, object]:
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

    product_pnl = metrics.get("final_pnl_by_product", {})
    return {
        "run_id": run_id,
        "total": float(metrics["final_pnl_total"]),
        "emeralds": float(product_pnl.get("EMERALDS", 0.0)),
        "tomatoes": float(product_pnl.get("TOMATOES", 0.0)),
        "trade_count": int(metrics.get("own_trade_count", 0)),
        "overrides": clone_overrides(overrides),
    }


def build_layers() -> List[SweepLayer]:
    return [
        SweepLayer(
            label="pressure micro coefficient",
            values=[0.25, 0.60, 1.00],
            description="How much microprice dislocation contributes to the pressure score.",
            apply=lambda overrides, value: set_value(overrides, "PRESSURE_MICRO_COEF", value),
        ),
        SweepLayer(
            label="pressure short momentum coefficient",
            values=[0.10, 0.20, 0.35],
            description="How much short-horizon momentum contributes to the pressure score.",
            apply=lambda overrides, value: set_value(overrides, "PRESSURE_SHORT_MOMENTUM_COEF", value),
        ),
        SweepLayer(
            label="pressure imbalance coefficient",
            values=[0.60, 1.20, 1.80],
            description="How strongly top-of-book imbalance contributes to the pressure score.",
            apply=lambda overrides, value: set_value(overrides, "PRESSURE_IMBALANCE_COEF", value),
        ),
        SweepLayer(
            label="pressure fair bonus",
            values=[0.15, 0.40, 0.80],
            description="How much the pressure score shifts TOMATOES fair value.",
            apply=lambda overrides, value: set_value(overrides, "PRESSURE_FAIR_BONUS", value),
        ),
        SweepLayer(
            label="pressure edge bonus",
            values=[0.00, 0.08, 0.20],
            description="How much the pressure score changes aggressive taking thresholds.",
            apply=lambda overrides, value: set_value(overrides, "PRESSURE_EDGE_BONUS", value),
        ),
        SweepLayer(
            label="pressure quote threshold",
            values=[0.90, 1.20, 1.60],
            description="How strong pressure must be before quote placement is nudged.",
            apply=lambda overrides, value: set_value(overrides, "PRESSURE_QUOTE_THRESHOLD", value),
        ),
        SweepLayer(
            label="tomatoes base quote edge",
            values=[2.00, 2.25, 2.50],
            description="How wide TOMATOES passive quotes sit before regime adjustments.",
            apply=lambda overrides, value: set_value(overrides, "BASE_QUOTE_EDGE", value),
        ),
        SweepLayer(
            label="tomatoes base take edge",
            values=[1.35, 1.50, 1.65],
            description="How much raw edge TOMATOES needs before taking liquidity.",
            apply=lambda overrides, value: set_value(overrides, "BASE_TAKE_EDGE", value),
        ),
    ]


def write_csv(results: List[Dict[str, object]]) -> None:
    with CSV_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "run_id",
                "label",
                "tested_value",
                "total_pnl",
                "emeralds_pnl",
                "tomatoes_pnl",
                "trade_count",
            ]
        )
        for result in results:
            writer.writerow(
                [
                    result["run_id"],
                    result["label"],
                    result["tested_value"],
                    f"{result['total']:.1f}",
                    f"{result['emeralds']:.1f}",
                    f"{result['tomatoes']:.1f}",
                    result["trade_count"],
                ]
            )


def write_report(
    baseline_result: Dict[str, object],
    final_result: Dict[str, object],
    sections: List[str],
    best_layer: Dict[str, object],
) -> None:
    lines = [
        "V17 Microstructure Sweep",
        "",
        "Method",
        "- Rust backtester on workspace day -1",
        f"- Trader: {TRADER_PATH.name}",
        "- Search style: layered TOMATOES-only parameter sweep",
        "- Important note: use this for local direction, not as an official PnL estimate",
        "",
        "Baseline",
        f"- Total: {baseline_result['total']:.1f}",
        f"- EMERALDS: {baseline_result['emeralds']:.1f}",
        f"- TOMATOES: {baseline_result['tomatoes']:.1f}",
        "",
        "Best Layered Result",
        f"- Total: {final_result['total']:.1f}",
        f"- EMERALDS: {final_result['emeralds']:.1f}",
        f"- TOMATOES: {final_result['tomatoes']:.1f}",
        f"- Trade count: {final_result['trade_count']}",
        f"- Overrides: {json.dumps(final_result['overrides'], sort_keys=True)}",
        "",
        "Most Sensitive Layer",
        f"- {best_layer['label']} with a local total-PnL spread of {best_layer['spread']:.1f}",
        "",
    ]
    lines.extend(sections)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    if not BACKTESTER.exists():
        raise FileNotFoundError(f"Backtester binary not found: {BACKTESTER}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    defaults = load_v17_defaults()
    baseline_overrides = clone_overrides(defaults)
    layers = build_layers()

    results: List[Dict[str, object]] = []
    sections: List[str] = []
    layer_spreads: List[Dict[str, object]] = []

    baseline_result = run_backtest("v17-baseline", baseline_overrides)
    baseline_result.update({"label": "baseline", "tested_value": "defaults"})
    results.append(baseline_result)

    current_best_overrides = clone_overrides(defaults)
    current_best_result = baseline_result

    for index, layer in enumerate(layers, start=1):
        candidate_results: List[Dict[str, object]] = []

        for value in layer.values:
            candidate_overrides = clone_overrides(current_best_overrides)
            layer.apply(candidate_overrides, value)
            run_id = f"v17-l{index}-{sanitize_run_component(layer.label)}-{sanitize_run_component(format_value(value))}"
            result = run_backtest(run_id, candidate_overrides)
            result.update({"label": layer.label, "tested_value": format_value(value)})
            candidate_results.append(result)
            results.append(result)

        candidate_results.sort(key=lambda row: (row["total"], row["tomatoes"], row["emeralds"]), reverse=True)
        best_candidate = candidate_results[0]
        worst_candidate = candidate_results[-1]

        current_best_overrides = clone_overrides(best_candidate["overrides"])
        current_best_result = best_candidate

        spread = float(best_candidate["total"]) - float(worst_candidate["total"])
        layer_spreads.append({"label": layer.label, "spread": spread})

        sections.extend(
            [
                f"Layer {index}: {layer.label}",
                f"- Why it matters: {layer.description}",
                f"- Best value: {best_candidate['tested_value']} -> total {best_candidate['total']:.1f} | TOMATOES {best_candidate['tomatoes']:.1f}",
                f"- Worst value: {worst_candidate['tested_value']} -> total {worst_candidate['total']:.1f}",
                f"- Layer spread: {spread:.1f}",
                "",
            ]
        )

    final_result = run_backtest("v17-layered-best", current_best_overrides)
    final_result.update({"label": "layered_best_confirmation", "tested_value": "combined"})
    results.append(final_result)

    layer_spreads.sort(key=lambda row: row["spread"], reverse=True)
    best_layer = layer_spreads[0]

    write_csv(results)
    write_report(baseline_result, final_result, sections, best_layer)

    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {CSV_PATH}")
    print(f"Baseline {baseline_result['total']:.1f} -> layered best {final_result['total']:.1f}")


if __name__ == "__main__":
    main()
