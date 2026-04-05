import json
import os
import subprocess
from itertools import product
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "ProsperityRustBacktester" / "runs"
BOT = ROOT / "Bots" / "Traderv23_local.py"
BACKTESTER = ROOT / "ProsperityRustBacktester" / "target" / "debug" / "rust_backtester"


BASE_CARRY_WEIGHTS = [0.40, 0.55, 0.70]
TREND_CARRY_BONUSES = [0.10, 0.20]
STRETCH_FADE_BONUSES = [0.10, 0.25]


def run_case(base_weight: float, trend_bonus: float, stretch_bonus: float) -> dict:
    run_id = f"Traderv23-sweep-bw{int(base_weight*100)}-tb{int(trend_bonus*100)}-sb{int(stretch_bonus*100)}"
    env = os.environ.copy()
    env["V23_BASE_CARRY_WEIGHT"] = str(base_weight)
    env["V23_TREND_CARRY_BONUS"] = str(trend_bonus)
    env["V23_STRETCH_FADE_BONUS"] = str(stretch_bonus)

    subprocess.run(
        [
            str(BACKTESTER),
            "--trader",
            str(BOT),
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
            str(RUNS),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    metrics_path = RUNS / run_id / "metrics.json"
    metrics = json.loads(metrics_path.read_text())
    return {
        "run_id": run_id,
        "base_carry_weight": base_weight,
        "trend_carry_bonus": trend_bonus,
        "stretch_fade_bonus": stretch_bonus,
        "total": metrics["final_pnl_total"],
        "emeralds": metrics["final_pnl_by_product"]["EMERALDS"],
        "tomatoes": metrics["final_pnl_by_product"]["TOMATOES"],
    }


def main() -> None:
    results = []
    for base_weight, trend_bonus, stretch_bonus in product(
        BASE_CARRY_WEIGHTS,
        TREND_CARRY_BONUSES,
        STRETCH_FADE_BONUSES,
    ):
        results.append(run_case(base_weight, trend_bonus, stretch_bonus))

    results.sort(key=lambda row: row["total"], reverse=True)
    for row in results:
        print(
            row["run_id"],
            row["total"],
            row["emeralds"],
            row["tomatoes"],
            row["base_carry_weight"],
            row["trend_carry_bonus"],
            row["stretch_fade_bonus"],
        )


if __name__ == "__main__":
    main()
