import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "Data"
OUTPUT_DIR = ROOT / "Analysis" / "output"

TRAIN_DAY = -2
TEST_DAY = -1
PRODUCT = "TOMATOES"

FEATURE_NAMES = [
    "micro_minus_mid",
    "imbalance_top",
    "imbalance_depth2",
    "spread",
    "spread_vs_avg3",
    "mom_1",
    "mom_3",
    "mom_8",
    "vol_3",
    "vol_8",
    "wall_mid_minus_mid",
    "best_bid_change",
    "best_ask_change",
]

CANDIDATE_HORIZONS = [1, 2, 3, 4, 5, 8]
CANDIDATE_ALPHAS = [0.0, 0.01, 0.10, 1.0, 5.0, 10.0]


@dataclass
class BookRow:
    day: int
    timestamp: int
    bid_1: int
    bid_vol_1: int
    bid_2: int
    bid_vol_2: int
    ask_1: int
    ask_vol_1: int
    ask_2: int
    ask_vol_2: int
    mid_price: float


def parse_int(value: str, default: int = 0) -> int:
    if value == "":
        return default
    return int(float(value))


def parse_float(value: str, default: float = 0.0) -> float:
    if value == "":
        return default
    return float(value)


def load_rows(day: int) -> List[BookRow]:
    path = DATA_DIR / f"prices_round_0_day_{day}.csv"
    rows: List[BookRow] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for raw in reader:
            if raw["product"] != PRODUCT:
                continue
            rows.append(
                BookRow(
                    day=int(raw["day"]),
                    timestamp=int(raw["timestamp"]),
                    bid_1=parse_int(raw["bid_price_1"]),
                    bid_vol_1=parse_int(raw["bid_volume_1"]),
                    bid_2=parse_int(raw["bid_price_2"], parse_int(raw["bid_price_1"])),
                    bid_vol_2=parse_int(raw["bid_volume_2"]),
                    ask_1=parse_int(raw["ask_price_1"]),
                    ask_vol_1=parse_int(raw["ask_volume_1"]),
                    ask_2=parse_int(raw["ask_price_2"], parse_int(raw["ask_price_1"])),
                    ask_vol_2=parse_int(raw["ask_volume_2"]),
                    mid_price=parse_float(raw["mid_price"]),
                )
            )
    if not rows:
        raise RuntimeError(f"no {PRODUCT} rows in {path}")
    return rows


def rolling_average(values: List[float], window: int, fallback: float) -> float:
    subset = values[-window:]
    if not subset:
        return fallback
    return sum(subset) / len(subset)


def rolling_abs_return(values: List[float], window: int) -> float:
    subset = values[-window:]
    if len(subset) < 2:
        return 0.0
    diffs = [abs(subset[index] - subset[index - 1]) for index in range(1, len(subset))]
    return sum(diffs) / len(diffs)


def build_dataset(rows: List[BookRow], horizon: int) -> Tuple[np.ndarray, np.ndarray]:
    features: List[List[float]] = []
    mids: List[float] = []
    bids: List[float] = []
    asks: List[float] = []
    spreads: List[float] = []

    for row in rows:
        spread = row.ask_1 - row.bid_1
        top_total = max(1, row.bid_vol_1 + row.ask_vol_1)
        depth_total = max(1, row.bid_vol_1 + row.bid_vol_2 + row.ask_vol_1 + row.ask_vol_2)
        micro = ((row.bid_1 * row.ask_vol_1) + (row.ask_1 * row.bid_vol_1)) / top_total
        wall_mid = (row.bid_2 + row.ask_2) / 2.0

        average_3 = rolling_average(mids, 3, row.mid_price)
        average_8 = rolling_average(mids, 8, row.mid_price)
        average_spread_3 = rolling_average(spreads, 3, spread)

        previous_bid = bids[-1] if bids else row.bid_1
        previous_ask = asks[-1] if asks else row.ask_1
        previous_mid = mids[-1] if mids else row.mid_price

        features.append(
            [
                micro - row.mid_price,
                (row.bid_vol_1 - row.ask_vol_1) / top_total,
                (row.bid_vol_1 + row.bid_vol_2 - row.ask_vol_1 - row.ask_vol_2) / depth_total,
                spread,
                spread - average_spread_3,
                row.mid_price - previous_mid,
                row.mid_price - average_3,
                row.mid_price - average_8,
                rolling_abs_return(mids, 3),
                rolling_abs_return(mids, 8),
                wall_mid - row.mid_price,
                row.bid_1 - previous_bid,
                row.ask_1 - previous_ask,
            ]
        )

        mids.append(row.mid_price)
        bids.append(float(row.bid_1))
        asks.append(float(row.ask_1))
        spreads.append(float(spread))

    if len(features) <= horizon:
        raise RuntimeError(f"not enough rows for horizon {horizon}")

    x_matrix = np.asarray(features[:-horizon], dtype=float)
    target = np.asarray(
        [rows[index + horizon].mid_price - rows[index].mid_price for index in range(len(rows) - horizon)],
        dtype=float,
    )
    return x_matrix, target


def standardize(train_x: np.ndarray, test_x: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mean = train_x.mean(axis=0)
    std = train_x.std(axis=0)
    std[std < 1e-9] = 1.0
    return (train_x - mean) / std, (test_x - mean) / std, mean, std


def fit_ridge(train_x: np.ndarray, target: np.ndarray, alpha: float) -> np.ndarray:
    design = np.c_[np.ones(len(train_x)), train_x]
    xtx = design.T @ design
    ridge = np.eye(xtx.shape[0]) * alpha
    ridge[0, 0] = 0.0
    return np.linalg.solve(xtx + ridge, design.T @ target)


def predict(weights: np.ndarray, x_matrix: np.ndarray) -> np.ndarray:
    design = np.c_[np.ones(len(x_matrix)), x_matrix]
    return design @ weights


def evaluate(prediction: np.ndarray, actual: np.ndarray) -> Dict[str, float]:
    mse = float(np.mean((prediction - actual) ** 2))
    mae = float(np.mean(np.abs(prediction - actual)))
    corr = 0.0
    if np.std(prediction) > 1e-9 and np.std(actual) > 1e-9:
        corr = float(np.corrcoef(prediction, actual)[0, 1])
    directional_accuracy = float(np.mean((prediction * actual) > 0))
    directional_proxy = float(np.sum(np.sign(prediction) * actual))
    return {
        "mse": mse,
        "mae": mae,
        "corr": corr,
        "directional_accuracy": directional_accuracy,
        "directional_proxy": directional_proxy,
    }


def model_payload(horizon: int, alpha: float, mean: np.ndarray, std: np.ndarray, weights: np.ndarray) -> Dict[str, object]:
    return {
        "product": PRODUCT,
        "train_day": TRAIN_DAY,
        "test_day": TEST_DAY,
        "horizon": horizon,
        "alpha": alpha,
        "feature_names": FEATURE_NAMES,
        "intercept": float(weights[0]),
        "weights": [float(value) for value in weights[1:]],
        "means": [float(value) for value in mean],
        "stds": [float(value) for value in std],
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    train_rows = load_rows(TRAIN_DAY)
    test_rows = load_rows(TEST_DAY)

    results: List[Dict[str, object]] = []

    for horizon in CANDIDATE_HORIZONS:
        train_x, train_y = build_dataset(train_rows, horizon)
        test_x, test_y = build_dataset(test_rows, horizon)
        train_x_std, test_x_std, mean, std = standardize(train_x, test_x)

        for alpha in CANDIDATE_ALPHAS:
            weights = fit_ridge(train_x_std, train_y, alpha)
            train_pred = predict(weights, train_x_std)
            test_pred = predict(weights, test_x_std)

            train_metrics = evaluate(train_pred, train_y)
            test_metrics = evaluate(test_pred, test_y)
            payload = model_payload(horizon, alpha, mean, std, weights)

            results.append(
                {
                    "horizon": horizon,
                    "alpha": alpha,
                    "train": train_metrics,
                    "test": test_metrics,
                    "model": payload,
                }
            )

    best_by_mse = min(results, key=lambda item: float(item["test"]["mse"]))  # type: ignore[index]
    best_by_proxy = max(results, key=lambda item: float(item["test"]["directional_proxy"]))  # type: ignore[index]

    sorted_results = sorted(
        results,
        key=lambda item: (
            -float(item["test"]["directional_proxy"]),  # type: ignore[index]
            float(item["test"]["mse"]),  # type: ignore[index]
        ),
    )

    report_lines = [
        "Offline TOMATOES Model Report",
        "",
        f"Train day: {TRAIN_DAY}",
        f"Test day: {TEST_DAY}",
        f"Features: {', '.join(FEATURE_NAMES)}",
        "",
        "Best by holdout MSE:",
        json.dumps(
            {
                "horizon": best_by_mse["horizon"],
                "alpha": best_by_mse["alpha"],
                "test": best_by_mse["test"],
            },
            indent=2,
        ),
        "",
        "Best by holdout directional proxy:",
        json.dumps(
            {
                "horizon": best_by_proxy["horizon"],
                "alpha": best_by_proxy["alpha"],
                "test": best_by_proxy["test"],
            },
            indent=2,
        ),
        "",
        "Top candidates:",
    ]

    for candidate in sorted_results[:8]:
        report_lines.append(
            json.dumps(
                {
                    "horizon": candidate["horizon"],
                    "alpha": candidate["alpha"],
                    "train": candidate["train"],
                    "test": candidate["test"],
                },
                indent=2,
            )
        )

    (OUTPUT_DIR / "tomatoes_offline_model_report.txt").write_text("\n".join(report_lines))
    (OUTPUT_DIR / "tomatoes_offline_model_best_mse.json").write_text(
        json.dumps(best_by_mse["model"], indent=2)
    )
    (OUTPUT_DIR / "tomatoes_offline_model_best_proxy.json").write_text(
        json.dumps(best_by_proxy["model"], indent=2)
    )
    (OUTPUT_DIR / "tomatoes_offline_model_grid.json").write_text(
        json.dumps(
            [
                {
                    "horizon": result["horizon"],
                    "alpha": result["alpha"],
                    "train": result["train"],
                    "test": result["test"],
                }
                for result in sorted_results
            ],
            indent=2,
        )
    )

    print((OUTPUT_DIR / "tomatoes_offline_model_report.txt").relative_to(ROOT))
    print((OUTPUT_DIR / "tomatoes_offline_model_best_mse.json").relative_to(ROOT))
    print((OUTPUT_DIR / "tomatoes_offline_model_best_proxy.json").relative_to(ROOT))


if __name__ == "__main__":
    main()
