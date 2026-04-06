#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
DEFAULT_DAYS = (-2, -1)
RANDOM_SEED = 4101


@dataclass(frozen=True)
class ParameterSpec:
    block: str
    name: str
    lower: float
    upper: float
    initial: float
    sigma: float

    def clamp(self, value: float) -> float:
        return max(self.lower, min(self.upper, value))


PROFILES: Dict[str, Dict[str, object]] = {
    "55717_tomatoes": {
        "source_trader": WORKSPACE_ROOT / "Bots" / "55717.py",
        "generated_trader": WORKSPACE_ROOT / "Bots" / "55717_cmaes_candidate.py",
        "best_trader": WORKSPACE_ROOT / "Bots" / "55717_cmaes_best.py",
        "output_dir": WORKSPACE_ROOT / "Analysis" / "output" / "55717_cmaes",
        "specs": [
            ParameterSpec("EMERALDS", "REFERENCE_WEIGHT", 0.72, 0.86, 0.80, 0.02),
            ParameterSpec("EMERALDS", "MID_WEIGHT", 0.14, 0.28, 0.20, 0.02),
            ParameterSpec("EMERALDS", "INVENTORY_SKEW", 0.08, 0.16, 0.12, 0.01),
            ParameterSpec("EMERALDS", "SOFT_LIMIT_RATIO", 0.18, 0.34, 0.25, 0.02),
            ParameterSpec("TOMATOES", "INVENTORY_SKEW", 0.001, 0.015, 0.005, 0.002),
            ParameterSpec("TOMATOES", "BASE_TAKE_EDGE", 0.65, 1.00, 0.80, 0.06),
            ParameterSpec("TOMATOES", "BASE_QUOTE_EDGE", 2.40, 3.20, 2.75, 0.10),
            ParameterSpec("TOMATOES", "SOFT_LIMIT_RATIO", 0.45, 0.68, 0.56828726, 0.03),
            ParameterSpec("TOMATOES", "GAMMA_RANGE", 0.45, 0.90, 0.69283327, 0.06),
            ParameterSpec("TOMATOES", "RESERVATION_SCALE", 0.005, 0.06, 0.02, 0.008),
            ParameterSpec("TOMATOES", "SPREAD_INV_COEF", 0.70, 1.60, 1.1081637, 0.12),
            ParameterSpec("TOMATOES", "SPREAD_TIME_COEF", 1.00, 2.30, 1.7791177, 0.15),
            ParameterSpec("TOMATOES", "ALPHA_EDGE_SCALE", 1.15, 1.60, 1.4153631, 0.06),
            ParameterSpec("TOMATOES", "ALPHA_IMBALANCE_SCALE", 0.40, 1.00, 0.70, 0.08),
            ParameterSpec("TOMATOES", "RANGE_RESERVATION_BIAS", 0.15, 0.35, 0.26486122, 0.03),
            ParameterSpec("TOMATOES", "REGRESSION_HORIZON", 0.25, 1.20, 0.50, 0.12),
        ],
    },
    "v39_2_tomatoes": {
        "source_trader": WORKSPACE_ROOT / "Bots" / "Traderv39_2.py",
        "generated_trader": WORKSPACE_ROOT / "Bots" / "Traderv39_2_cmaes_candidate.py",
        "best_trader": WORKSPACE_ROOT / "Bots" / "Traderv39_2_cmaes_best.py",
        "output_dir": WORKSPACE_ROOT / "Analysis" / "output" / "v39_2_cmaes",
        "specs": [
            ParameterSpec("EMERALDS", "REFERENCE_WEIGHT", 0.72, 0.86, 0.80, 0.02),
            ParameterSpec("EMERALDS", "MID_WEIGHT", 0.14, 0.28, 0.20, 0.02),
            ParameterSpec("EMERALDS", "INVENTORY_SKEW", 0.02, 0.06, 0.0328922991, 0.006),
            ParameterSpec("EMERALDS", "SOFT_LIMIT_RATIO", 0.52, 0.72, 0.6357999832, 0.03),
            ParameterSpec("TOMATOES", "BASE_TAKE_EDGE", 0.72, 0.90, 0.78, 0.03),
            ParameterSpec("TOMATOES", "BASE_QUOTE_EDGE", 2.55, 2.95, 2.68, 0.05),
            ParameterSpec("TOMATOES", "SOFT_LIMIT_RATIO", 0.50, 0.65, 0.56828726, 0.02),
            ParameterSpec("TOMATOES", "ALPHA_EDGE_SCALE", 1.25, 1.55, 1.4153631, 0.04),
            ParameterSpec("TOMATOES", "RANGE_RESERVATION_BIAS", 0.18, 0.34, 0.26486122, 0.02),
            ParameterSpec("TOMATOES", "ALPHA_BLEND_WEIGHT", 0.10, 0.30, 0.28, 0.03),
            ParameterSpec("TOMATOES", "FAIR_ALPHA_WEIGHT", 0.20, 0.50, 0.42, 0.04),
            ParameterSpec("TOMATOES", "RANGE_ALPHA_DAMP", 0.20, 0.60, 0.35, 0.05),
            ParameterSpec("TOMATOES", "CONFLICT_ALPHA_DAMP", 0.30, 0.70, 0.45, 0.05),
            ParameterSpec("TOMATOES", "MOMENTUM_ALPHA_DAMP", 0.45, 0.90, 0.70, 0.05),
            ParameterSpec("TOMATOES", "POSITION_ALPHA_DAMP_START", 10.0, 20.0, 14.0, 1.5),
            ParameterSpec("TOMATOES", "POSITION_ALPHA_DAMP_END", 22.0, 34.0, 28.0, 1.8),
        ],
    },
    "v40_6_phase1": {
        "source_trader": WORKSPACE_ROOT / "Bots" / "Traderv40_6.py",
        "generated_trader": WORKSPACE_ROOT / "Bots" / "Traderv40_6_cmaes_candidate.py",
        "best_trader": WORKSPACE_ROOT / "Bots" / "Traderv40_6_cmaes_best.py",
        "output_dir": WORKSPACE_ROOT / "Analysis" / "output" / "v40_6_cmaes",
        "specs": [
            ParameterSpec("TOMATOES", "BASE_TAKE_EDGE", 0.68, 0.92, 0.78, 0.03),
            ParameterSpec("TOMATOES", "BASE_QUOTE_EDGE", 2.45, 2.95, 2.68, 0.05),
            ParameterSpec("TOMATOES", "SOFT_LIMIT_RATIO", 0.50, 0.66, 0.56828726, 0.02),
            ParameterSpec("TOMATOES", "ALPHA_EDGE_SCALE", 1.20, 1.60, 1.4153631, 0.05),
            ParameterSpec("TOMATOES", "ALPHA_BLEND_WEIGHT", 0.18, 0.38, 0.28, 0.03),
            ParameterSpec("TOMATOES", "FAIR_ALPHA_WEIGHT", 0.30, 0.54, 0.42, 0.04),
            ParameterSpec("TOMATOES", "RANGE_ALPHA_DAMP", 0.20, 0.48, 0.35, 0.04),
            ParameterSpec("TOMATOES", "CONFLICT_ALPHA_DAMP", 0.28, 0.62, 0.45, 0.04),
            ParameterSpec("TOMATOES", "POSITION_ALPHA_DAMP_START", 10.0, 18.0, 14.0, 1.2),
            ParameterSpec("TOMATOES", "POSITION_ALPHA_DAMP_END", 22.0, 34.0, 28.0, 1.6),
            ParameterSpec("TOMATOES", "REGIME_EWMA_ALPHA", 0.12, 0.32, 0.22, 0.03),
            ParameterSpec("TOMATOES", "LEAN_SCORE", 0.28, 0.58, 0.42, 0.04),
            ParameterSpec("TOMATOES", "STRONG_SCORE", 0.85, 1.35, 1.08, 0.07),
            ParameterSpec("TOMATOES", "DEFENSIVE_VOL_THRESHOLD", 2.8, 3.8, 3.3, 0.12),
        ],
    },
    "v40_8_2_phase1": {
        "source_trader": WORKSPACE_ROOT / "Bots" / "Traderv40_8_2.py",
        "generated_trader": WORKSPACE_ROOT / "Bots" / "Traderv40_8_2_cmaes_candidate.py",
        "best_trader": WORKSPACE_ROOT / "Bots" / "Traderv40_8_2_cmaes_best.py",
        "output_dir": WORKSPACE_ROOT / "Analysis" / "output" / "v40_8_2_cmaes",
        "specs": [
            ParameterSpec("TOMATOES", "BASE_TAKE_EDGE", 0.70, 0.82, 0.7516267301, 0.02),
            ParameterSpec("TOMATOES", "BASE_QUOTE_EDGE", 2.58, 2.74, 2.6470054123, 0.025),
            ParameterSpec("TOMATOES", "ALPHA_EDGE_SCALE", 1.28, 1.46, 1.3634015054, 0.025),
            ParameterSpec("TOMATOES", "ALPHA_BLEND_WEIGHT", 0.22, 0.32, 0.2658438089, 0.02),
            ParameterSpec("TOMATOES", "FAIR_ALPHA_WEIGHT", 0.36, 0.48, 0.420735319, 0.02),
            ParameterSpec("TOMATOES", "REGIME_EWMA_ALPHA", 0.18, 0.30, 0.2402714583, 0.02),
            ParameterSpec("TOMATOES", "LEAN_SCORE", 0.38, 0.50, 0.445547723, 0.02),
            ParameterSpec("TOMATOES", "STRONG_SCORE", 0.98, 1.14, 1.0628205438, 0.025),
            ParameterSpec("TOMATOES", "REENTRY_IMBALANCE_THRESHOLD", 0.08, 0.18, 0.13, 0.015),
            ParameterSpec("TOMATOES", "REENTRY_EDGE_BONUS", 0.02, 0.18, 0.08, 0.025),
            ParameterSpec("TOMATOES", "REENTRY_SIZE_BONUS", 0.0, 3.0, 1.0, 0.5),
            ParameterSpec("TOMATOES", "DEFENSIVE_VOL_THRESHOLD", 3.0, 3.8, 3.3735488393, 0.10),
        ],
    },
    "v40_7_day1_micro": {
        "source_trader": WORKSPACE_ROOT / "Bots" / "Traderv40_7.py",
        "generated_trader": WORKSPACE_ROOT / "Bots" / "Traderv40_7_cmaes_candidate.py",
        "best_trader": WORKSPACE_ROOT / "Bots" / "Traderv40_7_cmaes_best.py",
        "output_dir": WORKSPACE_ROOT / "Analysis" / "output" / "v40_7_cmaes_day1",
        "specs": [
            ParameterSpec("TOMATOES", "BASE_TAKE_EDGE", 0.72, 0.79, 0.7516267301, 0.015),
            ParameterSpec("TOMATOES", "BASE_QUOTE_EDGE", 2.60, 2.70, 2.6470054123, 0.02),
            ParameterSpec("TOMATOES", "ALPHA_EDGE_SCALE", 1.30, 1.42, 1.3634015054, 0.02),
            ParameterSpec("TOMATOES", "ALPHA_BLEND_WEIGHT", 0.24, 0.30, 0.2658438089, 0.015),
            ParameterSpec("TOMATOES", "REGIME_EWMA_ALPHA", 0.21, 0.28, 0.2402714583, 0.012),
            ParameterSpec("TOMATOES", "LEAN_SCORE", 0.41, 0.48, 0.445547723, 0.012),
            ParameterSpec("TOMATOES", "STRONG_SCORE", 1.01, 1.10, 1.0628205438, 0.015),
            ParameterSpec("TOMATOES", "DEFENSIVE_VOL_THRESHOLD", 3.15, 3.55, 3.3735488393, 0.06),
        ],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Focused CMA-ES tuner for fixed-structure bots.")
    parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
    parser.add_argument("--iterations", type=int, default=6)
    parser.add_argument("--population", type=int, default=10)
    parser.add_argument("--elite", type=int, default=4)
    parser.add_argument("--days", type=int, nargs="+", default=list(DEFAULT_DAYS))
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--inv-penalty", type=float, default=5.0)
    parser.add_argument("--stability-weight", type=float, default=0.20)
    parser.add_argument("--run-prefix", default="")
    parser.add_argument("--keep-runs", action="store_true")
    return parser.parse_args()


def ensure_dirs(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_root = output_dir / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    return run_root


def replace_in_block(content: str, block_name: str, key: str, value: float) -> str:
    block_pattern = rf'(DEFAULT_{block_name}_PARAMS\s*=\s*\{{)(.*?)(\n\}})'
    match = re.search(block_pattern, content, flags=re.S)
    if not match:
        raise RuntimeError(f"Missing block DEFAULT_{block_name}_PARAMS")
    block_body = match.group(2)
    replaced_body, count = re.subn(
        rf'("{re.escape(key)}":\s*)([^,\n]+)(,)',
        rf"\g<1>{repr(round(value, 10))}\g<3>",
        block_body,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"Failed to replace parameter {block_name}.{key}")
    return content[: match.start(2)] + replaced_body + content[match.end(2) :]


def write_trader(source: Path, target: Path, params: Dict[Tuple[str, str], float]) -> None:
    content = source.read_text()
    for (block, key), value in params.items():
        content = replace_in_block(content, block, key, value)
    target.write_text(content)


def load_metrics(run_dir: Path) -> Dict[str, object]:
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        raise RuntimeError(f"Missing metrics: {metrics_path}")
    return json.loads(metrics_path.read_text())


def average_abs_tomatoes_inventory(submission_path: Path) -> float:
    data = json.loads(submission_path.read_text())
    activities_log = data.get("activitiesLog", "")
    trade_history = data.get("tradeHistory", [])
    net_by_timestamp: Dict[int, int] = {}
    for trade in trade_history:
        if trade.get("symbol") != "TOMATOES":
            continue
        timestamp = int(trade.get("timestamp", 0))
        if trade.get("buyer") == "SUBMISSION":
            net_by_timestamp[timestamp] = net_by_timestamp.get(timestamp, 0) + int(trade.get("quantity", 0))
        elif trade.get("seller") == "SUBMISSION":
            net_by_timestamp[timestamp] = net_by_timestamp.get(timestamp, 0) - int(trade.get("quantity", 0))

    reader = csv.DictReader(activities_log.splitlines(), delimiter=";")
    timestamps: List[int] = []
    for row in reader:
        if row.get("product") == "TOMATOES":
            timestamps.append(int(row["timestamp"]))

    if not timestamps:
        return 0.0

    position = 0
    abs_positions: List[float] = []
    for timestamp in timestamps:
        abs_positions.append(abs(position))
        position += net_by_timestamp.get(timestamp, 0)
    return sum(abs_positions) / len(abs_positions)


def run_backtest(trader_path: Path, run_root: Path, run_id: str, day: int) -> Dict[str, float]:
    run_dir = run_root / f"{run_id}-day{day}"
    if run_dir.exists():
        shutil.rmtree(run_dir)

    command = [
        str(BACKTESTER),
        "--trader",
        str(trader_path),
        "--dataset",
        "workspace",
        f"--day={day}",
        "--run-id",
        f"{run_id}-day{day}",
        "--products",
        "off",
        "--output-root",
        str(run_root),
    ]
    completed = subprocess.run(
        command,
        cwd=WORKSPACE_ROOT / "ProsperityRustBacktester",
        capture_output=True,
        text=True,
        check=True,
    )

    metrics = load_metrics(run_dir)
    submission_path = run_dir / "submission.log"
    if not submission_path.exists():
        raise RuntimeError(
            f"Missing submission.log for {run_id} day {day}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    pnl_by_product = metrics.get("final_pnl_by_product", {})
    return {
        "day": float(day),
        "total": float(metrics.get("final_pnl_total", 0.0)),
        "emeralds": float(pnl_by_product.get("EMERALDS", 0.0)),
        "tomatoes": float(pnl_by_product.get("TOMATOES", 0.0)),
        "own_trades": float(metrics.get("own_trade_count", 0)),
        "avg_abs_inventory": average_abs_tomatoes_inventory(submission_path),
    }


def objective_from_days(days: Sequence[Dict[str, float]], inv_penalty: float, stability_weight: float) -> Tuple[float, Dict[str, float]]:
    total = sum(day["total"] for day in days)
    tomatoes_total = sum(day["tomatoes"] for day in days)
    min_day_total = min(day["total"] for day in days)
    avg_inventory = sum(day["avg_abs_inventory"] for day in days) / len(days)
    inventory_penalty = inv_penalty * avg_inventory
    objective = total + (stability_weight * min_day_total) - inventory_penalty
    return objective, {
        "total": total,
        "tomatoes_total": tomatoes_total,
        "min_day_total": min_day_total,
        "avg_inventory": avg_inventory,
        "inventory_penalty": inventory_penalty,
    }


def evaluate_candidate(candidate_id: str, trader_path: Path, run_root: Path, days: Sequence[int], inv_penalty: float, stability_weight: float) -> Dict[str, object]:
    day_results = [run_backtest(trader_path, run_root, candidate_id, day) for day in days]
    objective, summary = objective_from_days(day_results, inv_penalty, stability_weight)
    return {"candidate_id": candidate_id, "objective": objective, "days": day_results, **summary}


def weighted_mean(candidates: Sequence[List[float]], weights: Sequence[float]) -> List[float]:
    total = sum(weights)
    dims = len(candidates[0])
    return [sum(candidate[index] * weight for candidate, weight in zip(candidates, weights)) / total for index in range(dims)]


def weighted_variance(candidates: Sequence[List[float]], weights: Sequence[float], mean: Sequence[float]) -> List[float]:
    total = sum(weights)
    dims = len(candidates[0])
    return [
        sum(weight * ((candidate[index] - mean[index]) ** 2) for candidate, weight in zip(candidates, weights)) / total
        for index in range(dims)
    ]


def param_label(spec: ParameterSpec) -> str:
    return f"{spec.block}.{spec.name}"


def serialize_params(params: Dict[Tuple[str, str], float]) -> Dict[str, float]:
    return {f"{block}.{name}": value for (block, name), value in params.items()}


class SeparableCMAES:
    def __init__(self, specs: Sequence[ParameterSpec], seed: int) -> None:
        self.specs = list(specs)
        self.rng = random.Random(seed)
        self.mean = [spec.initial for spec in self.specs]
        self.sigma = [spec.sigma for spec in self.specs]

    def sample(self, population: int) -> List[Dict[str, object]]:
        samples: List[Dict[str, object]] = []
        for _ in range(population):
            vector = []
            for index, spec in enumerate(self.specs):
                candidate = self.mean[index] + self.sigma[index] * self.rng.gauss(0.0, 1.0)
                vector.append(spec.clamp(candidate))
            params = {(spec.block, spec.name): vector[index] for index, spec in enumerate(self.specs)}
            samples.append({"vector": vector, "params": params})
        return samples

    def update(self, elites: Sequence[Dict[str, object]]) -> None:
        if not elites:
            return
        elite_vectors = [list(candidate["vector"]) for candidate in elites]
        elite_count = len(elites)
        weights = [math.log(elite_count + 1.0) - math.log(index + 1.0) for index in range(elite_count)]
        new_mean = weighted_mean(elite_vectors, weights)
        new_variance = weighted_variance(elite_vectors, weights, new_mean)
        for index, spec in enumerate(self.specs):
            blended_mean = 0.65 * self.mean[index] + 0.35 * new_mean[index]
            blended_sigma = 0.70 * self.sigma[index] + 0.30 * max(spec.sigma * 0.35, math.sqrt(max(1e-12, new_variance[index])))
            self.mean[index] = spec.clamp(blended_mean)
            self.sigma[index] = max(spec.sigma * 0.20, min(spec.sigma * 2.50, blended_sigma))


def write_csv(csv_path: Path, results: Sequence[Dict[str, object]], specs: Sequence[ParameterSpec]) -> None:
    fieldnames = [
        "candidate_id", "iteration", "rank", "objective", "total", "tomatoes_total", "min_day_total", "avg_inventory", "inventory_penalty"
    ] + [param_label(spec) for spec in specs]
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            row = {key: item.get(key) for key in fieldnames}
            params = item.get("params", {})
            if isinstance(params, dict):
                for spec in specs:
                    row[param_label(spec)] = params.get((spec.block, spec.name))
            writer.writerow(row)


def write_report(report_path: Path, args: argparse.Namespace, specs: Sequence[ParameterSpec], baseline_result: Dict[str, object], best_result: Dict[str, object]) -> None:
    lines = [
        "Focused Bot CMA-ES",
        "==================",
        "",
        f"Profile: {args.profile}",
        f"Days: {', '.join(str(day) for day in args.days)}",
        f"Iterations: {args.iterations}",
        f"Population: {args.population}",
        f"Elite: {args.elite}",
        f"Seed: {args.seed}",
        f"Inventory penalty: {args.inv_penalty}",
        f"Stability weight: {args.stability_weight}",
        "",
        "Parameters:",
    ]
    for spec in specs:
        lines.append(f"- {spec.block}.{spec.name}: start {spec.initial}, range [{spec.lower}, {spec.upper}], sigma {spec.sigma}")
    lines.extend([
        "",
        "Baseline:",
        f"- objective: {baseline_result['objective']:.3f}",
        f"- total: {baseline_result['total']:.3f}",
        f"- tomatoes_total: {baseline_result['tomatoes_total']:.3f}",
        f"- min_day_total: {baseline_result['min_day_total']:.3f}",
        f"- avg_inventory: {baseline_result['avg_inventory']:.3f}",
        "",
        "Best:",
        f"- candidate_id: {best_result['candidate_id']}",
        f"- objective: {best_result['objective']:.3f}",
        f"- total: {best_result['total']:.3f}",
        f"- tomatoes_total: {best_result['tomatoes_total']:.3f}",
        f"- min_day_total: {best_result['min_day_total']:.3f}",
        f"- avg_inventory: {best_result['avg_inventory']:.3f}",
        "",
        "Best Parameters:",
    ])
    for (block, key), value in best_result["params"].items():
        lines.append(f"- {block}.{key}: {value:.6f}")
    lines.extend(["", "Per-Day Best Candidate:"])
    for day_result in best_result["days"]:
        lines.append(
            f"- day {int(day_result['day'])}: total {day_result['total']:.3f}, tomatoes {day_result['tomatoes']:.3f}, emeralds {day_result['emeralds']:.3f}, avg_inventory {day_result['avg_abs_inventory']:.3f}"
        )
    report_path.write_text("\n".join(lines) + "\n")


def maybe_cleanup_runs(run_root: Path, keep_runs: bool) -> None:
    if keep_runs:
        return
    for run_dir in run_root.iterdir():
        if run_dir.is_dir():
            shutil.rmtree(run_dir)


def main() -> None:
    args = parse_args()
    profile = PROFILES[args.profile]
    source_trader = profile["source_trader"]
    generated_trader = profile["generated_trader"]
    best_trader = profile["best_trader"]
    output_dir = profile["output_dir"]
    specs = profile["specs"]
    run_root = ensure_dirs(output_dir)
    csv_path = output_dir / "results.csv"
    report_path = output_dir / "report.txt"
    state_path = output_dir / "best_state.json"

    run_prefix = args.run_prefix or args.profile.replace("_", "-")
    optimizer = SeparableCMAES(specs, args.seed)
    baseline_params = {(spec.block, spec.name): spec.initial for spec in specs}

    write_trader(source_trader, generated_trader, baseline_params)
    baseline_result = evaluate_candidate(f"{run_prefix}-baseline", generated_trader, run_root, args.days, args.inv_penalty, args.stability_weight)
    baseline_result.update({"iteration": -1, "rank": 0, "params": baseline_params})
    best_result: Dict[str, object] = dict(baseline_result)
    write_trader(source_trader, best_trader, best_result["params"])
    all_results: List[Dict[str, object]] = [baseline_result]

    for iteration in range(args.iterations):
        samples = optimizer.sample(args.population)
        evaluated: List[Dict[str, object]] = []
        for candidate_index, sample in enumerate(samples):
            candidate_id = f"{run_prefix}-it{iteration:02d}-cand{candidate_index:02d}"
            write_trader(source_trader, generated_trader, sample["params"])
            result = evaluate_candidate(candidate_id, generated_trader, run_root, args.days, args.inv_penalty, args.stability_weight)
            result.update({"iteration": iteration, "params": sample["params"], "vector": sample["vector"]})
            evaluated.append(result)
        evaluated.sort(key=lambda item: float(item["objective"]), reverse=True)
        elites = []
        for rank, result in enumerate(evaluated, start=1):
            result["rank"] = rank
            all_results.append(result)
            if rank <= args.elite:
                elites.append({"vector": result["vector"], "params": result["params"]})
        optimizer.update(elites)
        if float(evaluated[0]["objective"]) > float(best_result["objective"]):
            best_result = dict(evaluated[0])
            write_trader(source_trader, best_trader, best_result["params"])

    serializable_best = dict(best_result)
    serializable_best["params"] = serialize_params(best_result["params"])
    state_path.write_text(json.dumps(serializable_best, indent=2))
    write_csv(csv_path, all_results, specs)
    write_report(report_path, args, specs, baseline_result, best_result)
    maybe_cleanup_runs(run_root, args.keep_runs)

    print(f"profile: {args.profile}")
    print(f"baseline objective: {baseline_result['objective']:.3f}")
    print(f"best objective: {best_result['objective']:.3f}")
    print(f"best total: {best_result['total']:.3f}")
    print(f"best tomatoes_total: {best_result['tomatoes_total']:.3f}")
    print(f"best avg_inventory: {best_result['avg_inventory']:.3f}")
    print(f"best trader: {best_trader}")
    print(f"report: {report_path}")
    print(f"results: {csv_path}")


if __name__ == "__main__":
    main()
