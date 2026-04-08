#!/usr/bin/env python3
"""
CMA-ES parameter optimization for Traderv31.

Optimizes 11 active TOMATOES parameters using (5_w, 10)-CMA-ES.
Objective: average PnL across day -1 AND day -2 (prevents overfitting with only 2 days of data).

Usage (from repo root):
    python3 Analysis/v31_cmaes_optimize.py

Outputs:
    Analysis/output/v31_cmaes_best.json
    Analysis/output/v31_cmaes_report.txt
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE_PATH = Path(
    "/Users/vasudravinarendran/Documents/Prosperity/MyProsperity/Bots/Traderv31.py"
)
BACKTESTER = ROOT / "Backtest_failed_Python" / "run_backtest.py"
OUTPUT_DIR = ROOT / "Analysis" / "output"

# ---------------------------------------------------------------------------
# Baselines (from V31 default backtest)
# ---------------------------------------------------------------------------
BASELINES = {"day_neg1": 13726.0, "day_neg2": 13661.0}
OVERFIT_SLACK = 150.0  # accept day-2 result if >= baseline - slack

# ---------------------------------------------------------------------------
# Parameters to optimise
# ---------------------------------------------------------------------------
PARAM_NAMES = [
    "GAMMA_RANGE",
    "RESERVATION_SCALE",
    "RANGE_RESERVATION_BIAS",
    "SPREAD_VOL_COEF",
    "SPREAD_INV_COEF",
    "SPREAD_TIME_COEF",
    "BASE_TAKE_EDGE",
    "ALPHA_EDGE_SCALE",
    "ALPHA_IMBALANCE_SCALE",
    "INVENTORY_SKEW",
    "SOFT_LIMIT_RATIO",
]

PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "GAMMA_RANGE":            (0.05, 0.80),
    "RESERVATION_SCALE":      (0.02, 0.40),
    "RANGE_RESERVATION_BIAS": (0.02, 0.60),
    "SPREAD_VOL_COEF":        (0.10, 2.50),
    "SPREAD_INV_COEF":        (0.05, 1.50),
    "SPREAD_TIME_COEF":       (0.10, 2.00),
    "BASE_TAKE_EDGE":         (0.80, 1.80),
    "ALPHA_EDGE_SCALE":       (0.70, 1.50),
    "ALPHA_IMBALANCE_SCALE":  (0.70, 1.80),
    "INVENTORY_SKEW":         (0.005, 0.15),
    "SOFT_LIMIT_RATIO":       (0.30, 0.90),
}

PARAM_DEFAULTS: dict[str, float] = {
    "GAMMA_RANGE":            0.34,
    "RESERVATION_SCALE":      0.12,
    "RANGE_RESERVATION_BIAS": 0.20,
    "SPREAD_VOL_COEF":        0.90,
    "SPREAD_INV_COEF":        0.42,
    "SPREAD_TIME_COEF":       0.90,
    "BASE_TAKE_EDGE":         1.25,
    "ALPHA_EDGE_SCALE":       1.06,
    "ALPHA_IMBALANCE_SCALE":  1.16,
    "INVENTORY_SKEW":         0.035,
    "SOFT_LIMIT_RATIO":       0.65,
}

# ---------------------------------------------------------------------------
# Parameter injection
# ---------------------------------------------------------------------------

def inject_params(source: str, params: dict[str, float]) -> str:
    """
    Replace parameter values inside DEFAULT_TOMATOES_PARAMS only.
    Uses brace-counting to isolate the block, avoiding collision with
    DEFAULT_EMERALDS_PARAMS which shares INVENTORY_SKEW and SOFT_LIMIT_RATIO.
    """
    marker = "DEFAULT_TOMATOES_PARAMS = {"
    start = source.find(marker)
    if start == -1:
        raise ValueError("DEFAULT_TOMATOES_PARAMS not found in source")

    brace_depth = 0
    end = start
    for i in range(start, len(source)):
        if source[i] == "{":
            brace_depth += 1
        elif source[i] == "}":
            brace_depth -= 1
            if brace_depth == 0:
                end = i + 1
                break

    block = source[start:end]
    for name, value in params.items():
        pattern = rf'("{re.escape(name)}":\s*)[\d.eE+\-]+'
        replacement = rf"\g<1>{value:.8g}"
        block = re.sub(pattern, replacement, block)

    return source[:start] + block + source[end:]


# ---------------------------------------------------------------------------
# Backtest runner — one subprocess per eval, no import os
# ---------------------------------------------------------------------------

_eval_count = 0


def run_with_params(source: str, params: dict[str, float], day: int) -> float:
    """Write a patched copy of V31, run the backtester, return total PnL."""
    global _eval_count
    _eval_count += 1

    tmp_stem = f"v31_cmaes_{uuid.uuid4().hex}"
    tmp_dir = Path(tempfile.gettempdir())
    tmp_bot = tmp_dir / f"{tmp_stem}.py"
    tmp_out = tmp_dir / tmp_stem

    try:
        tmp_bot.write_text(inject_params(source, params))
        result = subprocess.run(
            [
                sys.executable,
                str(BACKTESTER),
                str(tmp_bot),
                "--day", str(day),
                "--output", str(tmp_out),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        for line in result.stdout.splitlines():
            if line.startswith("Final total PnL:"):
                return float(line.split(":")[1].strip())
        # Failed run — return large penalty
        print(f"  [WARN] eval {_eval_count} day={day} failed. stderr: {result.stderr[:200]}")
        return -1e9
    finally:
        if tmp_bot.exists():
            tmp_bot.unlink()
        if tmp_out.exists():
            shutil.rmtree(tmp_out, ignore_errors=True)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def normalize(params: dict[str, float]) -> np.ndarray:
    x = np.zeros(len(PARAM_NAMES))
    for i, name in enumerate(PARAM_NAMES):
        lo, hi = PARAM_BOUNDS[name]
        x[i] = (params[name] - lo) / (hi - lo)
    return x


def denormalize(x: np.ndarray) -> dict[str, float]:
    result = {}
    for i, name in enumerate(PARAM_NAMES):
        lo, hi = PARAM_BOUNDS[name]
        result[name] = lo + float(np.clip(x[i], 0.0, 1.0)) * (hi - lo)
    return result


# ---------------------------------------------------------------------------
# CMA-ES — pure numpy, (5_w, 10)-CMA-ES
# ---------------------------------------------------------------------------

def run_cmaes(
    source: str,
    x0: np.ndarray,
    sigma0: float = 0.20,
    lam: int = 10,
    mu: int = 5,
    max_iter: int = 25,
    seed: int = 42,
) -> tuple[np.ndarray, float, list[dict]]:
    """
    Minimise objective = -PnL(day=-1) using CMA-ES.

    Returns:
        best_x   : best normalised parameter vector found (clamped to [0,1])
        best_pnl : best day-1 PnL achieved
        history  : list of per-generation dicts for reporting
    """
    rng = np.random.default_rng(seed)
    n = len(x0)

    # --- Static constants (Hansen & Ostermeier notation) ---
    raw_w = np.array([np.log((lam + 1) / 2) - np.log(i) for i in range(1, mu + 1)])
    weights = raw_w / raw_w.sum()
    mu_eff = 1.0 / np.sum(weights ** 2)

    c_c = (4 + mu_eff / n) / (n + 4 + 2 * mu_eff / n)
    c_sigma = (mu_eff + 2) / (n + mu_eff + 5)
    d_sigma = 1 + c_sigma + 2 * max(0.0, np.sqrt((mu_eff - 1) / (n + 1)) - 1)
    c_1 = 2.0 / ((n + 1.3) ** 2 + mu_eff)
    c_mu = min(1.0 - c_1, 2.0 * (mu_eff - 0.25) / ((n + 2) ** 2 + mu_eff))
    chi_n = np.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n ** 2))

    # --- State ---
    mean = x0.copy()
    C = np.eye(n)
    sigma = sigma0
    p_c = np.zeros(n)
    p_s = np.zeros(n)

    best_x = np.clip(mean, 0.0, 1.0)
    best_pnl = -np.inf
    history: list[dict] = []

    print(f"CMA-ES start | n={n} | lam={lam} | mu={mu} | max_iter={max_iter} | sigma0={sigma0}")
    print(f"Total budget: ~{lam * max_iter} evals")
    print()

    for gen in range(1, max_iter + 1):
        # 1. Cholesky of C (with PD guard)
        try:
            L = np.linalg.cholesky(C)
        except np.linalg.LinAlgError:
            C += 1e-8 * np.eye(n)
            L = np.linalg.cholesky(C)

        # 2. Sample lam offspring
        z = rng.standard_normal((lam, n))
        y = (L @ z.T).T                        # N(0, C) samples
        x = mean + sigma * y                   # candidate points (unclamped)
        x_eval = np.clip(x, 0.0, 1.0)         # clamp only for evaluation

        # 3. Evaluate — average of both days to prevent overfitting
        fitness = np.array(
            [
                -(
                    run_with_params(source, denormalize(x_eval[k]), day=-1)
                    + run_with_params(source, denormalize(x_eval[k]), day=-2)
                ) / 2.0
                for k in range(lam)
            ]
        )  # negative avg PnL so we minimise

        # 4. Sort, select mu best
        sorted_idx = np.argsort(fitness)
        best_idx = sorted_idx[:mu]

        # Track global best
        gen_best_pnl = -fitness[sorted_idx[0]]
        if gen_best_pnl > best_pnl:
            best_pnl = gen_best_pnl
            best_x = x_eval[sorted_idx[0]].copy()

        # 5. Update mean (use unclamped x for state update)
        mean_old = mean.copy()
        mean = np.sum(weights[:, None] * x[best_idx], axis=0)

        # 6. Step vectors in C-space
        y_best = (x[best_idx] - mean_old) / sigma   # shape (mu, n)
        y_w = np.sum(weights[:, None] * y_best, axis=0)

        # 7. Update evolution path p_sigma
        C_inv_half_y_w = np.linalg.solve(L.T, y_w)
        p_s = (
            (1 - c_sigma) * p_s
            + np.sqrt(c_sigma * (2 - c_sigma) * mu_eff) * C_inv_half_y_w
        )

        # 8. Update sigma
        sigma = sigma * np.exp((c_sigma / d_sigma) * (np.linalg.norm(p_s) / chi_n - 1))
        sigma = float(np.clip(sigma, 1e-4, 1.0))

        # 9. h_sigma indicator
        expected_ps_norm = np.sqrt(1 - (1 - c_sigma) ** (2 * gen))
        h_sigma = 1 if (np.linalg.norm(p_s) / expected_ps_norm) < (1.4 + 2.0 / (n + 1)) * chi_n else 0

        # 10. Update evolution path p_c
        p_c = (
            (1 - c_c) * p_c
            + h_sigma * np.sqrt(c_c * (2 - c_c) * mu_eff) * y_w
        )

        # 11. Update covariance matrix
        delta_h = (1 - h_sigma) * c_c * (2 - c_c)
        rank1 = np.outer(p_c, p_c)
        rank_mu = sum(weights[i] * np.outer(y_best[i], y_best[i]) for i in range(mu))
        C = (
            (1 - c_1 - c_mu) * C
            + c_1 * (rank1 + delta_h * C)
            + c_mu * rank_mu
        )
        C = (C + C.T) / 2.0  # enforce symmetry

        gen_record = {
            "gen": gen,
            "best_avg_pnl_this_gen": gen_best_pnl,
            "global_best_avg_pnl": best_pnl,
            "sigma": sigma,
            "mean_avg_pnl": -float(np.mean(fitness)),
        }
        history.append(gen_record)

        print(
            f"Gen {gen:3d}/{max_iter} | "
            f"gen_best_avg={gen_best_pnl:.2f} | "
            f"global_best_avg={best_pnl:.2f} | "
            f"sigma={sigma:.5f} | "
            f"evals={_eval_count}"
        )

    return best_x, best_pnl, history


# ---------------------------------------------------------------------------
# Overfitting guard
# ---------------------------------------------------------------------------

def check_results(
    source: str,
    best_x: np.ndarray,
) -> tuple[dict[str, float], float, float, bool]:
    """
    Evaluate best candidate on both days individually.
    Since both days were used in training, there is no held-out test —
    we report both and flag if either day regresses vs baseline.
    Returns: (best_params, day1_pnl, day2_pnl, any_regression)
    """
    best_params = denormalize(best_x)

    print("\nFinal evaluation of best candidate on both days ...")
    day1_pnl = run_with_params(source, best_params, day=-1)
    day2_pnl = run_with_params(source, best_params, day=-2)

    any_regression = day1_pnl < BASELINES["day_neg1"] or day2_pnl < BASELINES["day_neg2"]
    print(f"  Day -1 PnL: {day1_pnl:.2f}  ({day1_pnl - BASELINES['day_neg1']:+.2f} vs baseline)")
    print(f"  Day -2 PnL: {day2_pnl:.2f}  ({day2_pnl - BASELINES['day_neg2']:+.2f} vs baseline)")
    if any_regression:
        print("  WARNING: one or both days regressed vs baseline.")

    return best_params, day1_pnl, day2_pnl, any_regression


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_results(
    best_params: dict[str, float],
    best_pnl_d1: float,
    best_pnl_d2: float,
    any_regression: bool,
    history: list[dict],
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON
    avg_pnl = (best_pnl_d1 + best_pnl_d2) / 2.0
    output = {
        **best_params,
        "meta": {
            "day_neg1_pnl": round(best_pnl_d1, 4),
            "day_neg2_pnl": round(best_pnl_d2, 4),
            "avg_pnl": round(avg_pnl, 4),
            "baseline_day_neg1": BASELINES["day_neg1"],
            "baseline_day_neg2": BASELINES["day_neg2"],
            "baseline_avg": round((BASELINES["day_neg1"] + BASELINES["day_neg2"]) / 2, 4),
            "delta_day_neg1": round(best_pnl_d1 - BASELINES["day_neg1"], 4),
            "delta_day_neg2": round(best_pnl_d2 - BASELINES["day_neg2"], 4),
            "delta_avg": round(avg_pnl - (BASELINES["day_neg1"] + BASELINES["day_neg2"]) / 2, 4),
            "any_regression_vs_baseline": any_regression,
            "total_evaluations": _eval_count,
            "objective": "avg(day-1, day-2)",
        },
        "history": history,
    }
    json_path = OUTPUT_DIR / "v31_cmaes_best.json"
    json_path.write_text(json.dumps(output, indent=2))

    # Text report
    lines = [
        "V31 CMA-ES Optimization Report",
        "================================",
        "",
        f"Algorithm: (5_w, 10)-CMA-ES  |  n={len(PARAM_NAMES)}  |  sigma0=0.20  |  {len(history)} generations",
        f"Total evaluations: {_eval_count}",
        "",
        "Baselines",
        "---------",
        f"Day -1 baseline:  {BASELINES['day_neg1']:.2f}",
        f"Day -2 baseline:  {BASELINES['day_neg2']:.2f}",
        f"Avg baseline:     {(BASELINES['day_neg1'] + BASELINES['day_neg2']) / 2:.2f}",
        "",
        "Best Result",
        "-----------",
        f"Day -1 PnL:   {best_pnl_d1:.2f}   ({best_pnl_d1 - BASELINES['day_neg1']:+.2f} vs baseline)",
        f"Day -2 PnL:   {best_pnl_d2:.2f}   ({best_pnl_d2 - BASELINES['day_neg2']:+.2f} vs baseline)",
        f"Avg PnL:      {(best_pnl_d1 + best_pnl_d2) / 2:.2f}   ({(best_pnl_d1 + best_pnl_d2)/2 - (BASELINES['day_neg1']+BASELINES['day_neg2'])/2:+.2f} vs baseline avg)",
        f"Note: both days used in objective — no held-out test available.",
        "",
        "Parameter Comparison",
        "--------------------",
        f"{'Parameter':<26} {'Default':>10} {'Optimized':>12} {'Change':>10}",
        "-" * 62,
    ]
    for name in PARAM_NAMES:
        default = PARAM_DEFAULTS[name]
        optimized = best_params[name]
        pct = (optimized - default) / default * 100 if default != 0 else 0
        lines.append(f"{name:<26} {default:>10.4f} {optimized:>12.4f} {pct:>+9.1f}%")

    lines += [
        "",
        "Generation History",
        "------------------",
        f"{'Gen':>4}  {'Gen Best':>10}  {'Global Best':>12}  {'Sigma':>8}",
    ]
    for r in history:
        lines.append(
            f"{r['gen']:4d}  {r['best_avg_pnl_this_gen']:10.2f}  {r['global_best_avg_pnl']:12.2f}  {r['sigma']:8.5f}"
        )

    lines += [
        "",
        "Recommendation",
        "--------------",
    ]
    if any_regression:
        lines.append("WARNING: one or both days regressed vs baseline. Review before submitting.")
    else:
        lines.append("Both days improved vs baseline. Apply to Traderv32.py:")
        lines.append("Update DEFAULT_TOMATOES_PARAMS with values in v31_cmaes_best.json.")

    report_path = OUTPUT_DIR / "v31_cmaes_report.txt"
    report_path.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {json_path}")
    print(f"Wrote {report_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not BOT_SOURCE_PATH.exists():
        raise FileNotFoundError(f"Bot not found: {BOT_SOURCE_PATH}")
    if not BACKTESTER.exists():
        raise FileNotFoundError(f"Backtester not found: {BACKTESTER}")

    source = BOT_SOURCE_PATH.read_text()

    # Sanity-check inject_params on a known value
    test_patched = inject_params(source, {"GAMMA_RANGE": 0.999})
    assert "0.999" in test_patched, "inject_params failed sanity check"
    # Verify EMERALDS INVENTORY_SKEW is untouched
    emerald_block_end = source.find("DEFAULT_TOMATOES_PARAMS")
    assert '"INVENTORY_SKEW": 0.12' in source[:emerald_block_end], \
        "EMERALDS INVENTORY_SKEW sanity check failed"
    print("Param injection sanity check passed.")

    # Start from default parameter values
    x0 = normalize(PARAM_DEFAULTS)
    print(f"Initial x0 range: [{x0.min():.3f}, {x0.max():.3f}] (should be well inside [0,1])")

    # Run CMA-ES (optimise on day -1 only)
    best_x, best_pnl_d1, history = run_cmaes(
        source=source,
        x0=x0,
        sigma0=0.20,
        lam=10,
        mu=5,
        max_iter=25,
        seed=42,
    )

    # Evaluate best candidate on both days individually
    best_params, day1_pnl, day2_pnl, any_regression = check_results(source, best_x)

    # Save outputs
    save_results(best_params, day1_pnl, day2_pnl, any_regression, history)

    print("\nDone.")
    print(f"Day -1: {day1_pnl:.2f} ({day1_pnl - BASELINES['day_neg1']:+.2f})")
    print(f"Day -2: {day2_pnl:.2f} ({day2_pnl - BASELINES['day_neg2']:+.2f})")
    print(f"Avg:    {(day1_pnl + day2_pnl) / 2:.2f}")
    print(f"Total evals: {_eval_count}")


if __name__ == "__main__":
    main()
