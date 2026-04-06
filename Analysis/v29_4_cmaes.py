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
SOURCE_TRADER = WORKSPACE_ROOT / "Bots" / "Traderv29_4.py"
GENERATED_TRADER = WORKSPACE_ROOT / "Bots" / "Traderv29_4_cmaes_candidate.py"
BEST_TRADER = WORKSPACE_ROOT / "Bots" / "Traderv29_4_cmaes_best.py"
BACKTESTER = WORKSPACE_ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"
OUTPUT_DIR = WORKSPACE_ROOT / "Analysis" / "output" / "v29_4_cmaes"
RUN_OUTPUT_ROOT = OUTPUT_DIR / "runs"
CSV_PATH = OUTPUT_DIR / "results.csv"
REPORT_PATH = OUTPUT_DIR / "report.txt"
STATE_PATH = OUTPUT_DIR / "best_state.json"
DEFAULT_DAYS = (-2, -1)
RANDOM_SEED = 2940


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    lower: float
    upper: float
    initial: float
    sigma: float

    def clamp(self, value: float) -> float:
        return max(self.lower, min(self.upper, value))


PHASE1_SPECS: List[ParameterSpec] = [
    ParameterSpec("BASE_TAKE_EDGE", 0.80, 1.70, 1.25, 0.12),
    ParameterSpec("BASE_QUOTE_EDGE", 2.00, 3.40, 2.75, 0.18),
    ParameterSpec("INVENTORY_SKEW", 0.015, 0.060, 0.035, 0.006),
    ParameterSpec("SOFT_LIMIT_RATIO", 0.45, 0.78, 0.65, 0.04),
    ParameterSpec("TREND_EDGE_THRESHOLD", 0.70, 1.50, 1.00, 0.10),
    ParameterSpec("TREND_IMBALANCE_THRESHOLD", 0.06, 0.22, 0.12, 0.02),
    ParameterSpec("TOXIC_SPREAD_THRESHOLD", 13.0, 17.5, 15.0, 0.50),
    ParameterSpec("GAMMA_RANGE", 0.18, 0.55, 0.34, 0.04),
    ParameterSpec("GAMMA_TREND", 0.04, 0.18, 0.10, 0.02),
    ParameterSpec("GAMMA_VOLATILE", 0.20, 0.65, 0.40, 0.06),
    ParameterSpec("RESERVATION_SCALE", 0.05, 0.22, 0.12, 0.02),
    ParameterSpec("ALPHA_EDGE_SCALE", 0.90, 1.20, 1.06, 0.03),
    ParameterSpec("ALPHA_IMBALANCE_SCALE", 0.80, 1.40, 1.16, 0.08),
    ParameterSpec("POSITION_BIAS_DIVISOR", 8.0, 18.0, 12.0, 1.0),
]

PHASE2_SPECS: List[ParameterSpec] = PHASE1_SPECS + [
    ParameterSpec("TREND_FAIR_BONUS", 0.05, 0.40, 0.25, 0.04),
    ParameterSpec("TREND_ENTRY_TAKE_BONUS", 1.0, 5.0, 3.0, 0.6),
    ParameterSpec("TREND_HOLD_EXIT_BONUS", 0.20, 0.90, 0.55, 0.08),
    ParameterSpec("STRONG_TREND_HOLD_EXIT_BONUS", 0.40, 1.30, 0.90, 0.10),
]

PHASE3_SPECS: List[ParameterSpec] = PHASE2_SPECS + [
    ParameterSpec("TREND_SELL_HOLD_EXTRA", 0.00, 0.50, 0.24, 0.05),
    ParameterSpec("TREND_BUY_TAKE_EXTRA", 0.00, 0.20, 0.08, 0.03),
    ParameterSpec("TREND_QUOTE_LIFT_EXTRA", 0.0, 2.0, 1.0, 0.25),
    ParameterSpec("HOLD_TIME_COEF", 0.00, 0.16, 0.08, 0.02),
]

PHASE_SPECS = {
    "phase1": PHASE1_SPECS,
    "phase2": PHASE2_SPECS,
    "phase3": PHASE3_SPECS,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lightweight CMA-ES-style optimizer for Traderv29_4 TOMATOES.")
    parser.add_argument("--phase", choices=sorted(PHASE_SPECS), default="phase1")
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--population", type=int, default=10)
    parser.add_argument("--elite", type=int, default=5)
    parser.add_argument("--days", type=int, nargs="+", default=list(DEFAULT_DAYS))
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--inv-penalty", type=float, default=5.0)
    parser.add_argument("--stability-weight", type=float, default=0.20)
    parser.add_argument("--run-prefix", default="v29_4-cmaes")
    parser.add_argument("--init-state", default="")
    parser.add_argument("--keep-runs", action="store_true")
    return parser.parse_args()


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def write_trader(params: Dict[str, float], target: Path) -> None:
    content = SOURCE_TRADER.read_text()
    for key, value in params.items():
        content, count = re.subn(
            rf'("{re.escape(key)}":\s*)([^,\n]+)(,)',
            rf"\g<1>{repr(round(value, 10))}\g<3>",
            content,
            count=1,
        )
        if count != 1:
            raise RuntimeError(f"Failed to replace parameter {key}")
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


def run_backtest(trader_path: Path, run_id: str, day: int) -> Dict[str, float]:
    run_dir = RUN_OUTPUT_ROOT / f"{run_id}-day{day}"
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
        str(RUN_OUTPUT_ROOT),
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


def weighted_mean(candidates: Sequence[List[float]], weights: Sequence[float]) -> List[float]:
    total = sum(weights)
    dims = len(candidates[0])
    return [
        sum(candidate[index] * weight for candidate, weight in zip(candidates, weights)) / total
        for index in range(dims)
    ]


def weighted_variance(
    candidates: Sequence[List[float]],
    weights: Sequence[float],
    mean: Sequence[float],
) -> List[float]:
    total = sum(weights)
    dims = len(candidates[0])
    return [
        sum(weight * ((candidate[index] - mean[index]) ** 2) for candidate, weight in zip(candidates, weights)) / total
        for index in range(dims)
    ]


class SeparableCMAES:
    def __init__(self, specs: Sequence[ParameterSpec], seed: int) -> None:
        self.specs = list(specs)
        self.rng = random.Random(seed)
        self.mean = [spec.initial for spec in self.specs]
        self.sigma = [spec.sigma for spec in self.specs]

    def set_mean_from_params(self, params: Dict[str, float]) -> None:
        for index, spec in enumerate(self.specs):
            if spec.name in params:
                self.mean[index] = spec.clamp(float(params[spec.name]))

    def sample(self, population: int) -> List[Dict[str, object]]:
        samples: List[Dict[str, object]] = []
        for _ in range(population):
            vector = []
            for index, spec in enumerate(self.specs):
                candidate = self.mean[index] + self.sigma[index] * self.rng.gauss(0.0, 1.0)
                vector.append(spec.clamp(candidate))
            params = {spec.name: vector[index] for index, spec in enumerate(self.specs)}
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


def objective_from_days(
    days: Sequence[Dict[str, float]],
    inv_penalty: float,
    stability_weight: float,
) -> Tuple[float, Dict[str, float]]:
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


def evaluate_candidate(
    candidate_id: str,
    trader_path: Path,
    days: Sequence[int],
    inv_penalty: float,
    stability_weight: float,
) -> Dict[str, object]:
    day_results = [
        run_backtest(trader_path, candidate_id, day)
        for day in days
    ]
    objective, summary = objective_from_days(day_results, inv_penalty, stability_weight)
    return {
        "candidate_id": candidate_id,
        "objective": objective,
        "days": day_results,
        **summary,
    }


def write_csv(results: Sequence[Dict[str, object]], specs: Sequence[ParameterSpec]) -> None:
    fieldnames = [
        "candidate_id",
        "iteration",
        "rank",
        "objective",
        "total",
        "tomatoes_total",
        "min_day_total",
        "avg_inventory",
        "inventory_penalty",
    ] + [spec.name for spec in specs]
    with CSV_PATH.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            row = {key: item.get(key) for key in fieldnames}
            params = item.get("params", {})
            if isinstance(params, dict):
                for spec in specs:
                    row[spec.name] = params.get(spec.name)
            writer.writerow(row)


def write_report(
    args: argparse.Namespace,
    specs: Sequence[ParameterSpec],
    baseline_result: Dict[str, object],
    best_result: Dict[str, object],
) -> None:
    lines = [
        "V29.4 CMA-ES Tuning",
        "===================",
        "",
        f"Phase: {args.phase}",
        f"Days: {', '.join(str(day) for day in args.days)}",
        f"Iterations: {args.iterations}",
        f"Population: {args.population}",
        f"Elite: {args.elite}",
        f"Seed: {args.seed}",
        f"Inventory penalty: {args.inv_penalty}",
        f"Stability weight: {args.stability_weight}",
        "",
        "Phase Parameters:",
    ]
    for spec in specs:
        lines.append(
            f"- {spec.name}: start {spec.initial}, range [{spec.lower}, {spec.upper}], sigma {spec.sigma}"
        )

    lines.extend(
        [
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
        ]
    )
    for key, value in best_result["params"].items():
        lines.append(f"- {key}: {value:.6f}")

    lines.extend(["", "Per-Day Best Candidate:"])
    for day_result in best_result["days"]:
        lines.append(
            f"- day {int(day_result['day'])}: total {day_result['total']:.3f}, "
            f"tomatoes {day_result['tomatoes']:.3f}, emeralds {day_result['emeralds']:.3f}, "
            f"avg_inventory {day_result['avg_abs_inventory']:.3f}"
        )

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def maybe_cleanup_runs(keep_runs: bool) -> None:
    if keep_runs:
        return
    for run_dir in RUN_OUTPUT_ROOT.iterdir():
        if run_dir.is_dir():
            shutil.rmtree(run_dir)


def main() -> None:
    args = parse_args()
    ensure_dirs()
    specs = PHASE_SPECS[args.phase]
    optimizer = SeparableCMAES(specs, args.seed)

    best_result: Dict[str, object] | None = None
    all_results: List[Dict[str, object]] = []

    baseline_params = {spec.name: spec.initial for spec in specs}
    if args.init_state:
        init_path = Path(args.init_state)
        init_data = json.loads(init_path.read_text())
        init_params = init_data.get("params", {})
        if isinstance(init_params, dict):
            for spec in specs:
                if spec.name in init_params:
                    baseline_params[spec.name] = spec.clamp(float(init_params[spec.name]))
            optimizer.set_mean_from_params(baseline_params)
    write_trader(baseline_params, GENERATED_TRADER)
    baseline_result = evaluate_candidate(
        f"{args.run_prefix}-baseline",
        GENERATED_TRADER,
        args.days,
        args.inv_penalty,
        args.stability_weight,
    )
    baseline_result.update(
        {
            "iteration": -1,
            "rank": 0,
            "params": baseline_params,
        }
    )
    best_result = dict(baseline_result)
    write_trader(best_result["params"], BEST_TRADER)
    all_results.append(baseline_result)

    for iteration in range(args.iterations):
        samples = optimizer.sample(args.population)
        evaluated: List[Dict[str, object]] = []
        for candidate_index, sample in enumerate(samples):
            candidate_id = f"{args.run_prefix}-it{iteration:02d}-cand{candidate_index:02d}"
            write_trader(sample["params"], GENERATED_TRADER)
            result = evaluate_candidate(
                candidate_id,
                GENERATED_TRADER,
                args.days,
                args.inv_penalty,
                args.stability_weight,
            )
            result.update(
                {
                    "iteration": iteration,
                    "params": sample["params"],
                    "vector": sample["vector"],
                }
            )
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
            write_trader(best_result["params"], BEST_TRADER)

    STATE_PATH.write_text(json.dumps(best_result, indent=2))
    write_csv(all_results, specs)
    write_report(args, specs, baseline_result, best_result)
    maybe_cleanup_runs(args.keep_runs)

    print(f"phase: {args.phase}")
    print(f"baseline objective: {baseline_result['objective']:.3f}")
    print(f"best objective: {best_result['objective']:.3f}")
    print(f"best total: {best_result['total']:.3f}")
    print(f"best tomatoes_total: {best_result['tomatoes_total']:.3f}")
    print(f"best avg_inventory: {best_result['avg_inventory']:.3f}")
    print(f"best trader: {BEST_TRADER}")
    print(f"report: {REPORT_PATH}")
    print(f"results: {CSV_PATH}")


if __name__ == "__main__":
    main()
