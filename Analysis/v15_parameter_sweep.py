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
TRADER_PATH = WORKSPACE_ROOT / "Bots" / "Traderv15.py"
BOT_DIR = WORKSPACE_ROOT / "Bots"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "v15_sweep_runs"
REPORT_PATH = OUTPUT_DIR / "v15_sweep_report.txt"
CSV_PATH = OUTPUT_DIR / "v15_sweep_results.csv"
ENV_NAME = "TRADER_PARAM_OVERRIDES"


@dataclass
class SweepLayer:
    label: str
    product: str
    values: List[float]
    description: str
    apply: Callable[[Dict[str, Dict[str, float]], float], None]


def load_v15_defaults() -> Dict[str, Dict[str, float]]:
    sys.path.insert(0, str(BOT_DIR))
    spec = importlib.util.spec_from_file_location("traderv15_sweep_module", TRADER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {TRADER_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return {
        "EMERALDS": dict(module.DEFAULT_EMERALDS_PARAMS),
        "TOMATOES": dict(module.DEFAULT_TOMATOES_PARAMS),
    }


def clone_overrides(overrides: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    return {
        product: dict(values)
        for product, values in overrides.items()
    }


def set_value(overrides: Dict[str, Dict[str, float]], product: str, key: str, value: float) -> None:
    overrides.setdefault(product, {})[key] = value


def set_emeralds_reference_mix(overrides: Dict[str, Dict[str, float]], value: float) -> None:
    set_value(overrides, "EMERALDS", "REFERENCE_WEIGHT", value)
    set_value(overrides, "EMERALDS", "MID_WEIGHT", round(1.0 - value, 2))
    set_value(overrides, "EMERALDS", "MICRO_WEIGHT", 0.0)


def format_value(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}"


def sanitize_run_component(value: str) -> str:
    return value.replace(".", "p").replace("-", "m")


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
        "stdout": completed.stdout.strip(),
    }


def build_layers() -> List[SweepLayer]:
    return [
        SweepLayer(
            label="EMERALDS reference mix",
            product="EMERALDS",
            values=[0.75, 0.80, 0.85],
            description="Move anchor weight versus live mid weight.",
            apply=set_emeralds_reference_mix,
        ),
        SweepLayer(
            label="EMERALDS inventory skew",
            product="EMERALDS",
            values=[0.10, 0.12, 0.14],
            description="How strongly EMERALDS inventory shifts fair value.",
            apply=lambda overrides, value: set_value(overrides, "EMERALDS", "INVENTORY_SKEW", value),
        ),
        SweepLayer(
            label="EMERALDS take edge",
            product="EMERALDS",
            values=[0.85, 1.00, 1.15],
            description="How cheap/rich EMERALDS must look before crossing.",
            apply=lambda overrides, value: set_value(overrides, "EMERALDS", "BASE_TAKE_EDGE", value),
        ),
        SweepLayer(
            label="EMERALDS quote edge",
            product="EMERALDS",
            values=[1.75, 2.00, 2.25],
            description="How far EMERALDS passive quotes sit from fair value.",
            apply=lambda overrides, value: set_value(overrides, "EMERALDS", "BASE_QUOTE_EDGE", value),
        ),
        SweepLayer(
            label="EMERALDS passive size",
            product="EMERALDS",
            values=[6, 7, 8],
            description="Base size for passive EMERALDS quotes.",
            apply=lambda overrides, value: set_value(overrides, "EMERALDS", "PASSIVE_SIZE", value),
        ),
        SweepLayer(
            label="EMERALDS max take size",
            product="EMERALDS",
            values=[8, 10, 12],
            description="Maximum aggressive EMERALDS clip size.",
            apply=lambda overrides, value: set_value(overrides, "EMERALDS", "MAX_TAKE_SIZE", value),
        ),
        SweepLayer(
            label="EMERALDS soft limit ratio",
            product="EMERALDS",
            values=[0.45, 0.50, 0.55],
            description="When EMERALDS begins flattening more aggressively.",
            apply=lambda overrides, value: set_value(overrides, "EMERALDS", "SOFT_LIMIT_RATIO", value),
        ),
        SweepLayer(
            label="TOMATOES inventory skew",
            product="TOMATOES",
            values=[0.06, 0.08, 0.10],
            description="How strongly TOMATOES inventory shifts fair value.",
            apply=lambda overrides, value: set_value(overrides, "TOMATOES", "INVENTORY_SKEW", value),
        ),
        SweepLayer(
            label="TOMATOES take edge",
            product="TOMATOES",
            values=[1.20, 1.35, 1.50],
            description="How much edge TOMATOES needs before taking liquidity.",
            apply=lambda overrides, value: set_value(overrides, "TOMATOES", "BASE_TAKE_EDGE", value),
        ),
        SweepLayer(
            label="TOMATOES quote edge",
            product="TOMATOES",
            values=[1.75, 2.00, 2.25],
            description="How wide TOMATOES passive quotes sit around fair value.",
            apply=lambda overrides, value: set_value(overrides, "TOMATOES", "BASE_QUOTE_EDGE", value),
        ),
        SweepLayer(
            label="TOMATOES passive size",
            product="TOMATOES",
            values=[6, 7, 8],
            description="Base passive TOMATOES size before regime scaling.",
            apply=lambda overrides, value: set_value(overrides, "TOMATOES", "PASSIVE_SIZE", value),
        ),
        SweepLayer(
            label="TOMATOES max take size",
            product="TOMATOES",
            values=[7, 8, 9],
            description="Maximum aggressive TOMATOES clip size.",
            apply=lambda overrides, value: set_value(overrides, "TOMATOES", "MAX_TAKE_SIZE", value),
        ),
        SweepLayer(
            label="TOMATOES momentum weight",
            product="TOMATOES",
            values=[0.10, 0.20, 0.30],
            description="How much short momentum shifts TOMATOES fair value.",
            apply=lambda overrides, value: set_value(overrides, "TOMATOES", "MOMENTUM_WEIGHT", value),
        ),
        SweepLayer(
            label="TOMATOES imbalance weight",
            product="TOMATOES",
            values=[0.50, 0.70, 0.90],
            description="How much top-of-book imbalance shifts TOMATOES fair value.",
            apply=lambda overrides, value: set_value(overrides, "TOMATOES", "IMBALANCE_WEIGHT", value),
        ),
        SweepLayer(
            label="TOMATOES trend threshold",
            product="TOMATOES",
            values=[1.25, 1.50, 1.75],
            description="How easily TOMATOES switches into a trend regime.",
            apply=lambda overrides, value: set_value(overrides, "TOMATOES", "TREND_THRESHOLD", value),
        ),
    ]


def write_csv(results: List[Dict[str, object]]) -> None:
    with CSV_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "run_id",
                "label",
                "product",
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
                    result["product"],
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
    layer_sections: List[str],
    product_sensitivity: Dict[str, Dict[str, float]],
) -> None:
    lines = [
        "V15 Parameter Sweep",
        "",
        "Method",
        "- Rust backtester on workspace day -1",
        f"- Trader: {TRADER_PATH.name}",
        "- Search style: layered coordinate sweep",
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
        "Sensitivity Summary",
        f"- EMERALDS most sensitive layer spread: {product_sensitivity['EMERALDS']['label']} ({product_sensitivity['EMERALDS']['spread']:.1f} total PnL spread)",
        f"- TOMATOES most sensitive layer spread: {product_sensitivity['TOMATOES']['label']} ({product_sensitivity['TOMATOES']['spread']:.1f} total PnL spread)",
        "",
    ]
    lines.extend(layer_sections)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    if not BACKTESTER.exists():
        raise FileNotFoundError(f"Backtester binary not found: {BACKTESTER}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    defaults = load_v15_defaults()
    baseline_overrides = clone_overrides(defaults)
    layers = build_layers()

    results: List[Dict[str, object]] = []
    layer_sections: List[str] = []
    sensitivity_rows: List[Dict[str, object]] = []

    baseline_result = run_backtest("v15-baseline", baseline_overrides)
    baseline_result.update(
        {
            "label": "baseline",
            "product": "ALL",
            "tested_value": "defaults",
        }
    )
    results.append(baseline_result)

    current_best_overrides = clone_overrides(defaults)
    current_best_result = baseline_result

    for index, layer in enumerate(layers, start=1):
        candidate_results: List[Dict[str, object]] = []

        for value in layer.values:
            candidate_overrides = clone_overrides(current_best_overrides)
            layer.apply(candidate_overrides, value)
            run_id = f"v15-l{index}-{sanitize_run_component(layer.product.lower())}-{sanitize_run_component(layer.label.lower().replace(' ', '-'))}-{sanitize_run_component(format_value(value))}"
            result = run_backtest(run_id, candidate_overrides)
            result.update(
                {
                    "label": layer.label,
                    "product": layer.product,
                    "tested_value": format_value(value),
                }
            )
            candidate_results.append(result)
            results.append(result)

        candidate_results.sort(key=lambda row: (row["total"], row["emeralds"], row["tomatoes"]), reverse=True)
        best_candidate = candidate_results[0]
        worst_candidate = candidate_results[-1]
        best_value = next(
            value for value in layer.values if format_value(value) == best_candidate["tested_value"]
        )

        current_best_overrides = clone_overrides(best_candidate["overrides"])
        current_best_result = best_candidate

        sensitivity_rows.append(
            {
                "product": layer.product,
                "label": layer.label,
                "spread": float(best_candidate["total"]) - float(worst_candidate["total"]),
            }
        )

        section_lines = [
            f"Layer {index}: {layer.label}",
            f"- Product focus: {layer.product}",
            f"- Why it matters: {layer.description}",
            f"- Best value: {best_candidate['tested_value']} -> total {best_candidate['total']:.1f} | EMERALDS {best_candidate['emeralds']:.1f} | TOMATOES {best_candidate['tomatoes']:.1f}",
            f"- Worst value: {worst_candidate['tested_value']} -> total {worst_candidate['total']:.1f}",
            f"- Layer spread: {float(best_candidate['total']) - float(worst_candidate['total']):.1f}",
            f"- Applied going forward: {format_value(best_value)}",
            "",
        ]
        layer_sections.extend(section_lines)

    final_result = run_backtest("v15-layered-best", current_best_overrides)
    final_result.update(
        {
            "label": "layered_best_confirmation",
            "product": "ALL",
            "tested_value": "combined",
        }
    )
    results.append(final_result)

    product_sensitivity = {}
    for product in ["EMERALDS", "TOMATOES"]:
        matching_rows = [row for row in sensitivity_rows if row["product"] == product]
        matching_rows.sort(key=lambda row: row["spread"], reverse=True)
        top_row = matching_rows[0]
        product_sensitivity[product] = {
            "label": str(top_row["label"]),
            "spread": float(top_row["spread"]),
        }

    write_csv(results)
    write_report(baseline_result, final_result, layer_sections, product_sensitivity)

    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {CSV_PATH}")
    print(
        f"Baseline {baseline_result['total']:.1f} -> layered best {final_result['total']:.1f}"
    )


if __name__ == "__main__":
    main()
