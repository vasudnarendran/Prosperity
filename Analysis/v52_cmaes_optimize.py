#!/usr/bin/env python3
"""
Regularized CMA-ES for a tight follow-up search around Traderv52.

Why regularized and tight?
- v52 already improved on the official simulator.
- The next step is to refine the winning TOMATOES settings, not reopen a broad search.
- Local backtests are useful but still imperfect, so the objective penalizes:
  - regressions on either local day
  - uneven day-to-day gains
  - excessive drift away from the current v52 defaults

Usage:
    python3 Analysis/v52_cmaes_optimize.py
    python3 Analysis/v52_cmaes_optimize.py --max-iter 5 --population 6 --parents 3
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE_PATH = ROOT / "Bots" / "Traderv52.py"
BACKTESTER = ROOT / "Backtest_failed_Python" / "run_backtest.py"
OUTPUT_DIR = ROOT / "Analysis" / "output"

BASELINES = {
    "day_neg1": 15081.0,
    "day_neg2": 14803.0,
}

PARAM_NAMES = [
    "SPREAD_INV_COEF",
    "RESERVATION_SCALE",
    "BASE_TAKE_EDGE",
    "ALPHA_EDGE_SCALE",
    "ALPHA_IMBALANCE_SCALE",
    "PRESSURE_BIAS_SCALE",
    "BREAKOUT_QUOTE_TIGHTEN",
    "BREAKOUT_HOLD_BONUS",
]

PARAM_BOUNDS: Dict[str, tuple[float, float]] = {
    "SPREAD_INV_COEF": (0.90, 1.25),
    "RESERVATION_SCALE": (0.0080, 0.0175),
    "BASE_TAKE_EDGE": (0.48, 0.72),
    "ALPHA_EDGE_SCALE": (1.35, 1.72),
    "ALPHA_IMBALANCE_SCALE": (0.48, 0.74),
    "PRESSURE_BIAS_SCALE": (0.18, 0.33),
    "BREAKOUT_QUOTE_TIGHTEN": (0.09, 0.18),
    "BREAKOUT_HOLD_BONUS": (0.05, 0.11),
}

_eval_count = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tight regularized CMA-ES for Traderv52.")
    parser.add_argument("--max-iter", type=int, default=5, help="Number of CMA-ES generations.")
    parser.add_argument("--population", type=int, default=6, help="Population size (lambda).")
    parser.add_argument("--parents", type=int, default=3, help="Number of selected parents (mu).")
    parser.add_argument("--sigma0", type=float, default=0.06, help="Initial CMA-ES sigma.")
    parser.add_argument("--seed", type=int, default=52, help="Random seed.")
    parser.add_argument(
        "--regression-penalty",
        type=float,
        default=3.0,
        help="Penalty multiplier for local day regressions vs the current v52 baseline.",
    )
    parser.add_argument(
        "--imbalance-penalty",
        type=float,
        default=0.45,
        help="Penalty multiplier for uneven day-to-day deltas vs the baseline.",
    )
    parser.add_argument(
        "--drift-penalty",
        type=float,
        default=80.0,
        help="Penalty multiplier for normalized squared distance from current defaults.",
    )
    parser.add_argument(
        "--output-prefix",
        default="v52_cmaes_run1",
        help="Prefix for JSON/report outputs in Analysis/output.",
    )
    return parser.parse_args()


def extract_tomatoes_block(source: str) -> tuple[int, int, str]:
    marker = "DEFAULT_TOMATOES_PARAMS = {"
    start = source.find(marker)
    if start == -1:
        raise ValueError("DEFAULT_TOMATOES_PARAMS not found in source")

    brace_depth = 0
    end = start
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
            if brace_depth == 0:
                end = index + 1
                break

    return start, end, source[start:end]


def extract_defaults(source: str) -> Dict[str, float]:
    _start, _end, block = extract_tomatoes_block(source)
    defaults: Dict[str, float] = {}
    for name in PARAM_NAMES:
        match = re.search(rf'"{re.escape(name)}":\s*([\d.eE+\-]+)', block)
        if not match:
            raise ValueError(f"{name} not found inside DEFAULT_TOMATOES_PARAMS")
        defaults[name] = float(match.group(1))
    return defaults


def inject_params(source: str, params: Dict[str, float]) -> str:
    start, end, block = extract_tomatoes_block(source)
    for name, value in params.items():
        pattern = rf'("{re.escape(name)}":\s*)[\d.eE+\-]+'
        replacement = rf"\g<1>{value:.8g}"
        block = re.sub(pattern, replacement, block)
    return source[:start] + block + source[end:]


def parse_backtest_summary(stdout: str) -> float:
    for line in stdout.splitlines():
        if line.startswith("Final total PnL:"):
            return float(line.split(":", 1)[1].strip())
    raise RuntimeError(f"Unable to parse backtest summary:\n{stdout}")


def run_with_params(source: str, params: Dict[str, float], day: int) -> float:
    global _eval_count
    _eval_count += 1

    tmp_stem = f"v52_cmaes_{uuid.uuid4().hex}"
    tmp_dir = Path(tempfile.gettempdir())
    tmp_bot = tmp_dir / f"{tmp_stem}.py"
    tmp_out = tmp_dir / tmp_stem

    try:
        patched = inject_params(source, params)
        if not patched.endswith("\n"):
            patched += "\n"
        tmp_bot.write_text(patched)

        result = subprocess.run(
            [
                sys.executable,
                str(BACKTESTER),
                str(tmp_bot),
                "--day",
                str(day),
                "--output",
                str(tmp_out),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Backtester failed for day {day} with code {result.returncode}:\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        return parse_backtest_summary(result.stdout)
    finally:
        if tmp_bot.exists():
            tmp_bot.unlink()
        if tmp_out.exists():
            shutil.rmtree(tmp_out, ignore_errors=True)


def normalize(params: Dict[str, float]) -> np.ndarray:
    x = np.zeros(len(PARAM_NAMES))
    for index, name in enumerate(PARAM_NAMES):
        low, high = PARAM_BOUNDS[name]
        x[index] = (params[name] - low) / (high - low)
    return x


def denormalize(x: np.ndarray) -> Dict[str, float]:
    params: Dict[str, float] = {}
    for index, name in enumerate(PARAM_NAMES):
        low, high = PARAM_BOUNDS[name]
        params[name] = low + float(np.clip(x[index], 0.0, 1.0)) * (high - low)
    return params


def normalized_drift(params: Dict[str, float], defaults: Dict[str, float]) -> float:
    total = 0.0
    for name in PARAM_NAMES:
        low, high = PARAM_BOUNDS[name]
        scale = max(1e-9, high - low)
        total += ((params[name] - defaults[name]) / scale) ** 2
    return total / len(PARAM_NAMES)


def objective_value(
    day1: float,
    day2: float,
    params: Dict[str, float],
    defaults: Dict[str, float],
    args: argparse.Namespace,
) -> tuple[float, float, float, float]:
    avg = (day1 + day2) / 2.0
    regression_penalty = args.regression_penalty * (
        max(0.0, BASELINES["day_neg1"] - day1) + max(0.0, BASELINES["day_neg2"] - day2)
    )
    imbalance_penalty = args.imbalance_penalty * abs(
        (day1 - BASELINES["day_neg1"]) - (day2 - BASELINES["day_neg2"])
    )
    drift_penalty = args.drift_penalty * normalized_drift(params, defaults)
    objective = avg - regression_penalty - imbalance_penalty - drift_penalty
    return objective, regression_penalty, imbalance_penalty, drift_penalty


def evaluate_candidate(
    source: str,
    x: np.ndarray,
    defaults: Dict[str, float],
    args: argparse.Namespace,
) -> Dict[str, float]:
    params = denormalize(x)
    day1 = run_with_params(source, params, day=-1)
    day2 = run_with_params(source, params, day=-2)
    objective, regression_penalty, imbalance_penalty, drift_penalty = objective_value(
        day1,
        day2,
        params,
        defaults,
        args,
    )
    return {
        "day1": day1,
        "day2": day2,
        "avg": (day1 + day2) / 2.0,
        "objective": objective,
        "regression_penalty": regression_penalty,
        "imbalance_penalty": imbalance_penalty,
        "drift_penalty": drift_penalty,
        **params,
    }


def run_cmaes(
    source: str,
    defaults: Dict[str, float],
    x0: np.ndarray,
    args: argparse.Namespace,
) -> tuple[np.ndarray, Dict[str, float], List[Dict[str, float]]]:
    rng = np.random.default_rng(args.seed)
    n = len(x0)
    lam = args.population
    mu = args.parents

    raw_weights = np.array([np.log((lam + 1) / 2) - np.log(i) for i in range(1, mu + 1)])
    weights = raw_weights / raw_weights.sum()
    mu_eff = 1.0 / np.sum(weights ** 2)

    c_c = (4 + mu_eff / n) / (n + 4 + 2 * mu_eff / n)
    c_sigma = (mu_eff + 2) / (n + mu_eff + 5)
    d_sigma = 1 + c_sigma + 2 * max(0.0, np.sqrt((mu_eff - 1) / (n + 1)) - 1)
    c_1 = 2.0 / ((n + 1.3) ** 2 + mu_eff)
    c_mu = min(1.0 - c_1, 2.0 * (mu_eff - 0.25) / ((n + 2) ** 2 + mu_eff))
    chi_n = np.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n ** 2))

    mean = x0.copy()
    C = np.eye(n)
    sigma = args.sigma0
    p_c = np.zeros(n)
    p_s = np.zeros(n)

    best_x = np.clip(mean, 0.0, 1.0)
    best_eval = evaluate_candidate(source, best_x, defaults, args)
    best_objective = best_eval["objective"]
    history: List[Dict[str, float]] = []

    print(
        f"CMA-ES start | n={n} | lambda={lam} | mu={mu} | "
        f"max_iter={args.max_iter} | sigma0={args.sigma0}"
    )
    print(
        "Objective = avg(day-1, day-2)"
        " - regression_penalty - imbalance_penalty - drift_penalty"
    )
    print()

    for generation in range(1, args.max_iter + 1):
        try:
            L = np.linalg.cholesky(C)
        except np.linalg.LinAlgError:
            C += 1e-8 * np.eye(n)
            L = np.linalg.cholesky(C)

        z = rng.standard_normal((lam, n))
        y = (L @ z.T).T
        x = mean + sigma * y
        x_eval = np.clip(x, 0.0, 1.0)

        evaluations = [evaluate_candidate(source, x_eval[idx], defaults, args) for idx in range(lam)]
        fitness = np.array([-item["objective"] for item in evaluations])
        sorted_idx = np.argsort(fitness)
        best_idx = sorted_idx[:mu]

        gen_best = evaluations[sorted_idx[0]]
        if gen_best["objective"] > best_objective:
            best_objective = gen_best["objective"]
            best_x = x_eval[sorted_idx[0]].copy()
            best_eval = gen_best

        mean_old = mean.copy()
        mean = np.sum(weights[:, None] * x[best_idx], axis=0)

        y_best = (x[best_idx] - mean_old) / sigma
        y_w = np.sum(weights[:, None] * y_best, axis=0)
        C_inv_half_y_w = np.linalg.solve(L.T, y_w)

        p_s = (
            (1 - c_sigma) * p_s
            + np.sqrt(c_sigma * (2 - c_sigma) * mu_eff) * C_inv_half_y_w
        )

        sigma = sigma * np.exp((c_sigma / d_sigma) * (np.linalg.norm(p_s) / chi_n - 1))
        sigma = float(np.clip(sigma, 1e-4, 1.0))

        expected_ps_norm = np.sqrt(1 - (1 - c_sigma) ** (2 * generation))
        h_sigma = 1 if (np.linalg.norm(p_s) / expected_ps_norm) < (1.4 + 2.0 / (n + 1)) * chi_n else 0

        p_c = (
            (1 - c_c) * p_c
            + h_sigma * np.sqrt(c_c * (2 - c_c) * mu_eff) * y_w
        )

        delta_h = (1 - h_sigma) * c_c * (2 - c_c)
        rank1 = np.outer(p_c, p_c)
        rank_mu = sum(weights[i] * np.outer(y_best[i], y_best[i]) for i in range(mu))
        C = (
            (1 - c_1 - c_mu) * C
            + c_1 * (rank1 + delta_h * C)
            + c_mu * rank_mu
        )
        C = (C + C.T) / 2.0

        record = {
            "generation": generation,
            "gen_best_objective": gen_best["objective"],
            "gen_best_avg": gen_best["avg"],
            "global_best_objective": best_objective,
            "global_best_avg": best_eval["avg"],
            "sigma": sigma,
        }
        history.append(record)

        print(
            f"Gen {generation:2d}/{args.max_iter} | "
            f"gen_best_obj={gen_best['objective']:.2f} | "
            f"gen_best_avg={gen_best['avg']:.2f} | "
            f"global_best_obj={best_objective:.2f} | "
            f"global_best_avg={best_eval['avg']:.2f} | "
            f"sigma={sigma:.5f} | evals={_eval_count}"
        )

    return best_x, best_eval, history


def save_results(
    defaults: Dict[str, float],
    best_eval: Dict[str, float],
    history: List[Dict[str, float]],
    args: argparse.Namespace,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"{args.output_prefix}_best.json"
    report_path = OUTPUT_DIR / f"{args.output_prefix}_report.txt"

    output = {
        "params": {name: best_eval[name] for name in PARAM_NAMES},
        "meta": {
            "day_neg1": round(best_eval["day1"], 4),
            "day_neg2": round(best_eval["day2"], 4),
            "avg": round(best_eval["avg"], 4),
            "objective": round(best_eval["objective"], 4),
            "regression_penalty": round(best_eval["regression_penalty"], 4),
            "imbalance_penalty": round(best_eval["imbalance_penalty"], 4),
            "drift_penalty": round(best_eval["drift_penalty"], 4),
            "baseline_day_neg1": BASELINES["day_neg1"],
            "baseline_day_neg2": BASELINES["day_neg2"],
            "baseline_avg": round((BASELINES["day_neg1"] + BASELINES["day_neg2"]) / 2.0, 4),
            "total_evaluations": _eval_count,
            "seed": args.seed,
            "max_iter": args.max_iter,
            "population": args.population,
            "parents": args.parents,
            "sigma0": args.sigma0,
            "regression_penalty_weight": args.regression_penalty,
            "imbalance_penalty_weight": args.imbalance_penalty,
            "drift_penalty_weight": args.drift_penalty,
        },
        "history": history,
    }
    json_path.write_text(json.dumps(output, indent=2))

    lines = [
        "V52 Tight Regularized CMA-ES Report",
        "===================================",
        "",
        f"Bot source: {BOT_SOURCE_PATH}",
        f"Backtester: {BACKTESTER}",
        f"Total evaluations: {_eval_count}",
        "",
        "Baselines",
        "---------",
        f"Day -1 baseline: {BASELINES['day_neg1']:.2f}",
        f"Day -2 baseline: {BASELINES['day_neg2']:.2f}",
        f"Avg baseline:    {(BASELINES['day_neg1'] + BASELINES['day_neg2']) / 2.0:.2f}",
        "",
        "Best Candidate",
        "--------------",
        f"Day -1:      {best_eval['day1']:.2f}",
        f"Day -2:      {best_eval['day2']:.2f}",
        f"Avg:         {best_eval['avg']:.2f}",
        f"Objective:   {best_eval['objective']:.2f}",
        f"Reg penalty: {best_eval['regression_penalty']:.2f}",
        f"Imb penalty: {best_eval['imbalance_penalty']:.2f}",
        f"Drift pen.:  {best_eval['drift_penalty']:.2f}",
        "",
        "Parameter Changes",
        "-----------------",
        f"{'Parameter':<26} {'Default':>11} {'Best':>11} {'Delta %':>10}",
        "-" * 62,
    ]
    for name in PARAM_NAMES:
        default = defaults[name]
        best = best_eval[name]
        delta_pct = ((best - default) / default * 100.0) if abs(default) > 1e-9 else 0.0
        lines.append(f"{name:<26} {default:>11.5f} {best:>11.5f} {delta_pct:>+9.2f}%")

    lines += [
        "",
        "Generation History",
        "------------------",
        f"{'Gen':>4} {'Gen Obj':>12} {'Gen Avg':>12} {'Best Obj':>12} {'Best Avg':>12} {'Sigma':>8}",
    ]
    for record in history:
        lines.append(
            f"{record['generation']:4d} {record['gen_best_objective']:12.2f} "
            f"{record['gen_best_avg']:12.2f} {record['global_best_objective']:12.2f} "
            f"{record['global_best_avg']:12.2f} {record['sigma']:8.5f}"
        )

    report_path.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {json_path}")
    print(f"Wrote {report_path}")


def main() -> None:
    args = parse_args()
    if not BOT_SOURCE_PATH.exists():
        raise FileNotFoundError(f"Bot not found: {BOT_SOURCE_PATH}")
    if not BACKTESTER.exists():
        raise FileNotFoundError(f"Backtester not found: {BACKTESTER}")
    if args.parents > args.population:
        raise ValueError("--parents cannot exceed --population")

    source = BOT_SOURCE_PATH.read_text()
    defaults = extract_defaults(source)
    x0 = normalize(defaults)

    print("Running baseline sanity check on source defaults ...")
    base_day1 = run_with_params(source, defaults, day=-1)
    base_day2 = run_with_params(source, defaults, day=-2)
    print(f"Baseline day -1: {base_day1:.2f}")
    print(f"Baseline day -2: {base_day2:.2f}")
    if not math.isclose(base_day1, BASELINES["day_neg1"], abs_tol=1e-6) or not math.isclose(base_day2, BASELINES["day_neg2"], abs_tol=1e-6):
        print(
            "WARNING: source baseline differs from the expected v52 baseline. "
            "The optimizer will continue, but review the source before trusting the output."
        )
    print()

    best_x, best_eval, history = run_cmaes(source, defaults, x0, args)
    save_results(defaults, best_eval, history, args)

    print("\nDone.")
    print(f"Best objective: {best_eval['objective']:.2f}")
    print(f"Best avg PnL:   {best_eval['avg']:.2f}")
    print(f"Day -1:         {best_eval['day1']:.2f}")
    print(f"Day -2:         {best_eval['day2']:.2f}")


if __name__ == "__main__":
    main()
