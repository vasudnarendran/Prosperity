#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
BACKTESTER_PATH = ROOT / "Backtest_failed_Python" / "run_backtest.py"
OUTPUT_DIR = ROOT / "Analysis" / "output"
DEFAULT_BOT = ROOT / "Bots" / "Traderv52.py"
DEFAULT_COMPARE_BOT = ROOT / "Bots" / "Traderv51.py"


def load_backtester_module():
    spec = importlib.util.spec_from_file_location("prosperity_local_backtester", BACKTESTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load backtester from {BACKTESTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RB = load_backtester_module()


@dataclass(frozen=True)
class ScenarioFamily:
    name: str
    description: str
    path_mode: str
    block_steps_min: int
    block_steps_max: int
    passive_fill_prob_range: Tuple[float, float]
    passive_qty_scale_range: Tuple[float, float]
    aggressive_slip_prob_range: Tuple[float, float]
    aggressive_slip_ticks_range: Tuple[int, int]


@dataclass(frozen=True)
class DayScenario:
    family: str
    sample_index: int
    day: int
    path_mode: str
    block_steps: int
    passive_fill_prob: float
    passive_qty_scale: float
    aggressive_slip_prob: float
    aggressive_slip_ticks: int

    @property
    def sample_id(self) -> str:
        return f"{self.family}_{self.sample_index:03d}"


@dataclass
class ReplayDay:
    day: int
    ordered_timestamps: List[int]
    snapshots_by_timestamp: Dict[int, Dict[str, Any]]
    trades_by_timestamp_product: Dict[Tuple[int, str], List[Any]]
    step_interval: int
    source_timestamps: List[int]


@dataclass
class DayResult:
    bot: str
    family: str
    sample_id: str
    day: int
    total_pnl: float
    total_fills: int
    final_positions: Dict[str, int]
    product_pnl: Dict[str, float]
    block_steps: int
    passive_fill_prob: float
    passive_qty_scale: float
    aggressive_slip_prob: float
    aggressive_slip_ticks: int
    path_mode: str


FAMILY_LIBRARY: Dict[str, ScenarioFamily] = {
    "original_noise": ScenarioFamily(
        name="original_noise",
        description="Original historical path with very mild execution-noise perturbations.",
        path_mode="original",
        block_steps_min=0,
        block_steps_max=0,
        passive_fill_prob_range=(0.94, 1.00),
        passive_qty_scale_range=(0.96, 1.00),
        aggressive_slip_prob_range=(0.00, 0.03),
        aggressive_slip_ticks_range=(1, 1),
    ),
    "bootstrap_path": ScenarioFamily(
        name="bootstrap_path",
        description="Block-bootstrap of the historical path with no fill perturbation.",
        path_mode="bootstrap",
        block_steps_min=160,
        block_steps_max=520,
        passive_fill_prob_range=(1.00, 1.00),
        passive_qty_scale_range=(1.00, 1.00),
        aggressive_slip_prob_range=(0.00, 0.00),
        aggressive_slip_ticks_range=(1, 1),
    ),
    "bootstrap_balanced": ScenarioFamily(
        name="bootstrap_balanced",
        description="Block-bootstrap with calibrated mild-to-moderate execution degradation.",
        path_mode="bootstrap",
        block_steps_min=140,
        block_steps_max=420,
        passive_fill_prob_range=(0.84, 0.97),
        passive_qty_scale_range=(0.86, 0.97),
        aggressive_slip_prob_range=(0.01, 0.08),
        aggressive_slip_ticks_range=(1, 1),
    ),
    "bootstrap_stress": ScenarioFamily(
        name="bootstrap_stress",
        description="Block-bootstrap with stressed execution assumptions.",
        path_mode="bootstrap",
        block_steps_min=80,
        block_steps_max=240,
        passive_fill_prob_range=(0.68, 0.88),
        passive_qty_scale_range=(0.68, 0.85),
        aggressive_slip_prob_range=(0.05, 0.18),
        aggressive_slip_ticks_range=(1, 2),
    ),
}

PROFILE_LIBRARY: Dict[str, List[str]] = {
    "plausible": ["original_noise", "bootstrap_path", "bootstrap_balanced"],
    "stress": ["bootstrap_stress"],
    "all": list(FAMILY_LIBRARY.keys()),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monte Carlo robustness harness for Prosperity bots.")
    parser.add_argument(
        "--bot",
        default=str(DEFAULT_BOT),
        help="Primary bot path or bot filename. Defaults to Traderv52.py.",
    )
    parser.add_argument(
        "--compare-bot",
        default="",
        help="Optional comparison bot path or filename. Defaults to empty.",
    )
    parser.add_argument(
        "--days",
        nargs="*",
        type=int,
        default=[-1, -2],
        help="Day filters to include. Default: -1 -2",
    )
    parser.add_argument(
        "--samples-per-family",
        type=int,
        default=4,
        help="Number of Monte Carlo samples per scenario family.",
    )
    parser.add_argument(
        "--families",
        nargs="*",
        default=list(FAMILY_LIBRARY.keys()),
        help="Scenario families to run.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=52,
        help="Master random seed for scenario generation.",
    )
    parser.add_argument(
        "--output-prefix",
        default="v52_monte_carlo_run1",
        help="Prefix for report artifacts in Analysis/output.",
    )
    return parser.parse_args()


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(0.0, min(1.0, pct)) * (len(ordered) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize_distribution(values: List[float]) -> Dict[str, float]:
    if not values:
        return {
            "count": 0,
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "p10": 0.0,
            "p25": 0.0,
            "median": 0.0,
            "p75": 0.0,
            "p90": 0.0,
            "max": 0.0,
            "cvar10": 0.0,
        }

    ordered = sorted(float(value) for value in values)
    p10 = percentile(ordered, 0.10)
    tail = [value for value in ordered if value <= p10]
    return {
        "count": len(ordered),
        "mean": round(statistics.fmean(ordered), 4),
        "std": round(statistics.pstdev(ordered) if len(ordered) > 1 else 0.0, 4),
        "min": round(ordered[0], 4),
        "p10": round(p10, 4),
        "p25": round(percentile(ordered, 0.25), 4),
        "median": round(percentile(ordered, 0.50), 4),
        "p75": round(percentile(ordered, 0.75), 4),
        "p90": round(percentile(ordered, 0.90), 4),
        "max": round(ordered[-1], 4),
        "cvar10": round(statistics.fmean(tail), 4),
    }


def resolve_bot(bot_argument: str) -> Path:
    return RB.resolve_bot_path(bot_argument)


def build_original_day(
    day: int,
    prices_by_key: Dict[Tuple[int, int], Dict[str, Any]],
    market_trades_by_day: Dict[int, Dict[Tuple[int, str], List[Any]]],
    ordered_keys: List[Tuple[int, int]],
) -> ReplayDay:
    ordered_timestamps = [timestamp for price_day, timestamp in ordered_keys if price_day == day]
    if not ordered_timestamps:
        raise ValueError(f"No timestamps found for day {day}")

    step_interval = 100
    if len(ordered_timestamps) > 1:
        diffs = [ordered_timestamps[index] - ordered_timestamps[index - 1] for index in range(1, len(ordered_timestamps))]
        positive_diffs = [diff for diff in diffs if diff > 0]
        if positive_diffs:
            step_interval = int(statistics.median(positive_diffs))

    snapshots_by_timestamp: Dict[int, Dict[str, Any]] = {}
    for timestamp in ordered_timestamps:
        snapshots_by_timestamp[timestamp] = prices_by_key[(day, timestamp)]

    trades_by_timestamp_product = {
        (timestamp, product): list(trades)
        for (timestamp, product), trades in market_trades_by_day.get(day, {}).items()
    }

    return ReplayDay(
        day=day,
        ordered_timestamps=ordered_timestamps,
        snapshots_by_timestamp=snapshots_by_timestamp,
        trades_by_timestamp_product=trades_by_timestamp_product,
        step_interval=step_interval,
        source_timestamps=ordered_timestamps,
    )


def clone_trade(trade: Any, new_timestamp: int, TradeClass) -> Any:
    return TradeClass(
        symbol=trade.symbol,
        price=trade.price,
        quantity=trade.quantity,
        buyer=trade.buyer,
        seller=trade.seller,
        timestamp=new_timestamp,
    )


def bootstrap_day(
    base_day: ReplayDay,
    rng: random.Random,
    block_steps: int,
    TradeClass,
) -> ReplayDay:
    original_timestamps = list(base_day.ordered_timestamps)
    target_steps = len(original_timestamps)
    if target_steps == 0:
        raise ValueError("Cannot bootstrap an empty day")

    block_steps = max(1, min(block_steps, target_steps))
    new_timestamps: List[int] = []
    snapshots_by_timestamp: Dict[int, Dict[str, Any]] = {}
    trades_by_timestamp_product: Dict[Tuple[int, str], List[Any]] = {}

    while len(new_timestamps) < target_steps:
        remaining = target_steps - len(new_timestamps)
        current_block = min(block_steps, remaining)
        start_max = max(0, len(original_timestamps) - current_block)
        start_index = rng.randint(0, start_max)
        selected_block = original_timestamps[start_index : start_index + current_block]

        for original_timestamp in selected_block:
            new_timestamp = len(new_timestamps) * base_day.step_interval
            new_timestamps.append(new_timestamp)

            product_snapshots: Dict[str, Any] = {}
            for product, snapshot in base_day.snapshots_by_timestamp[original_timestamp].items():
                product_snapshots[product] = RB.Snapshot(
                    day=base_day.day,
                    timestamp=new_timestamp,
                    abs_timestamp=(base_day.day * 1_000_000) + new_timestamp,
                    product=product,
                    bid_levels=list(snapshot.bid_levels),
                    ask_levels=list(snapshot.ask_levels),
                    mid_price=snapshot.mid_price,
                )
            snapshots_by_timestamp[new_timestamp] = product_snapshots

            for product in product_snapshots:
                trades = base_day.trades_by_timestamp_product.get((original_timestamp, product), [])
                if trades:
                    trades_by_timestamp_product[(new_timestamp, product)] = [
                        clone_trade(trade, new_timestamp, TradeClass) for trade in trades
                    ]

    return ReplayDay(
        day=base_day.day,
        ordered_timestamps=new_timestamps,
        snapshots_by_timestamp=snapshots_by_timestamp,
        trades_by_timestamp_product=trades_by_timestamp_product,
        step_interval=base_day.step_interval,
        source_timestamps=original_timestamps,
    )


def scenario_rng(seed: int, family: str, sample_index: int, day: int) -> random.Random:
    return random.Random(f"{seed}:{family}:{sample_index}:{day}")


def sample_day_scenario(
    family: ScenarioFamily,
    sample_index: int,
    day: int,
    seed: int,
) -> DayScenario:
    rng = scenario_rng(seed, family.name, sample_index, day)

    block_steps = 0
    if family.path_mode == "bootstrap":
        block_steps = rng.randint(family.block_steps_min, family.block_steps_max)

    passive_fill_prob = rng.uniform(*family.passive_fill_prob_range)
    passive_qty_scale = rng.uniform(*family.passive_qty_scale_range)
    aggressive_slip_prob = rng.uniform(*family.aggressive_slip_prob_range)
    aggressive_slip_ticks = rng.randint(*family.aggressive_slip_ticks_range)

    return DayScenario(
        family=family.name,
        sample_index=sample_index,
        day=day,
        path_mode=family.path_mode,
        block_steps=block_steps,
        passive_fill_prob=passive_fill_prob,
        passive_qty_scale=passive_qty_scale,
        aggressive_slip_prob=aggressive_slip_prob,
        aggressive_slip_ticks=aggressive_slip_ticks,
    )


def stochastic_round(value: float, rng: random.Random) -> int:
    if value <= 0:
        return 0
    whole = int(math.floor(value))
    remainder = value - whole
    if rng.random() < remainder:
        whole += 1
    return whole


def execute_crossing_order_with_noise(order, snapshot: Any, side: str, day_scenario: DayScenario, rng: random.Random) -> Tuple[List[Any], int]:
    fills, remaining = RB.execute_crossing_order(order, snapshot, side)
    adjusted_fills: List[Any] = []

    for fill in fills:
        fill_price = fill.price
        fill_type = fill.fill_type
        if day_scenario.aggressive_slip_prob > 0 and rng.random() < day_scenario.aggressive_slip_prob:
            slip_ticks = max(0, int(day_scenario.aggressive_slip_ticks))
            if fill.side == "BUY":
                fill_price += slip_ticks
            else:
                fill_price -= slip_ticks
            fill_type = "aggressive_cross_mc_slip"

        adjusted_fills.append(
            RB.Fill(
                day=fill.day,
                timestamp=fill.timestamp,
                abs_timestamp=fill.abs_timestamp,
                product=fill.product,
                side=fill.side,
                price=fill_price,
                quantity=fill.quantity,
                fill_type=fill_type,
                source_order_price=fill.source_order_price,
            )
        )

    return adjusted_fills, remaining


def try_fill_pending_order_with_noise(
    order: Any,
    snapshot: Any,
    market_trades: List[Any],
    day_scenario: DayScenario,
    rng: random.Random,
) -> List[Any]:
    base_fillable = min(order.quantity, RB.pending_fill_quantity(order, snapshot, market_trades))
    if base_fillable <= 0:
        return []

    if rng.random() > day_scenario.passive_fill_prob:
        return []

    scaled_quantity = stochastic_round(base_fillable * day_scenario.passive_qty_scale, rng)
    fillable_quantity = min(order.quantity, scaled_quantity)
    if fillable_quantity <= 0:
        return []

    return [
        RB.Fill(
            day=snapshot.day,
            timestamp=snapshot.timestamp,
            abs_timestamp=snapshot.abs_timestamp,
            product=order.product,
            side=order.side,
            price=order.price,
            quantity=fillable_quantity,
            fill_type="passive_resting_fill_mc",
            source_order_price=order.price,
        )
    ]


def run_replay_day(
    bot_path: Path,
    replay_day: ReplayDay,
    day_scenario: DayScenario,
    datamodel: Tuple[Any, Any, Any, Any, Any, Any],
    listings: Dict[str, Any],
    seed: int,
) -> DayResult:
    (
        _ListingClass,
        ObservationClass,
        OrderClass,
        OrderDepthClass,
        TradeClass,
        TradingStateClass,
    ) = datamodel
    trader = RB.load_trader(bot_path)
    products = sorted(listings.keys())

    position = {product: 0 for product in products}
    cash = {product: 0.0 for product in products}
    pending_orders: Dict[str, List[Any]] = {product: [] for product in products}
    last_own_trades = RB.build_empty_own_trades(products)
    trader_data = ""
    total_fills = 0

    event_rng = random.Random(f"run:{seed}:{bot_path}:{day_scenario.sample_id}:{day_scenario.day}")

    for timestamp in replay_day.ordered_timestamps:
        snapshots = replay_day.snapshots_by_timestamp[timestamp]
        fills_between_steps: List[Any] = []

        for product in products:
            snapshot = snapshots[product]
            market_trades = replay_day.trades_by_timestamp_product.get((timestamp, product), [])
            for pending in pending_orders[product]:
                new_fills = try_fill_pending_order_with_noise(
                    pending,
                    snapshot,
                    market_trades,
                    day_scenario,
                    event_rng,
                )
                if new_fills:
                    fills_between_steps.extend(new_fills)
                # Pending orders expire after one interval in this local model.
            pending_orders[product] = []

        if fills_between_steps:
            total_fills += len(fills_between_steps)
            last_own_trades = RB.apply_fills(fills_between_steps, cash, position, TradeClass)

        order_depths = {
            product: RB.snapshot_to_order_depth(snapshots[product], OrderDepthClass) for product in products
        }
        market_trades = RB.build_market_trades(products, replay_day.trades_by_timestamp_product, timestamp)
        observations = ObservationClass({}, {})

        state = TradingStateClass(
            traderData=trader_data,
            timestamp=timestamp,
            listings=listings,
            order_depths=order_depths,
            own_trades=last_own_trades,
            market_trades=market_trades,
            position=dict(position),
            observations=observations,
        )

        stdout_buffer = io.StringIO()
        with redirect_stdout(stdout_buffer):
            orders_by_product, _conversions, trader_data = trader.run(state)

        step_fills: List[Any] = []
        for product, orders in orders_by_product.items():
            snapshot = snapshots[product]
            for order in orders:
                if not isinstance(order, OrderClass):
                    continue
                if order.quantity == 0:
                    continue

                side = "BUY" if order.quantity > 0 else "SELL"
                aggressive_fills, remaining_qty = execute_crossing_order_with_noise(
                    order,
                    snapshot,
                    side,
                    day_scenario,
                    event_rng,
                )
                step_fills.extend(aggressive_fills)

                if remaining_qty > 0:
                    resting_price = int(order.price)
                    is_resting = False
                    best_bid = snapshot.bid_levels[0][0]
                    best_ask = snapshot.ask_levels[0][0]
                    if side == "BUY" and resting_price < best_ask:
                        is_resting = True
                    if side == "SELL" and resting_price > best_bid:
                        is_resting = True
                    if is_resting:
                        pending_orders[product].append(
                            RB.PendingOrder(
                                product=product,
                                side=side,
                                price=resting_price,
                                quantity=remaining_qty,
                                day=replay_day.day,
                                timestamp=timestamp,
                            )
                        )

        if step_fills:
            total_fills += len(step_fills)
            last_own_trades = RB.apply_fills(step_fills, cash, position, TradeClass)
        else:
            last_own_trades = RB.build_empty_own_trades(products)

    if not replay_day.ordered_timestamps:
        raise ValueError("Replay day has no timestamps")

    final_timestamp = replay_day.ordered_timestamps[-1]
    final_snapshots = replay_day.snapshots_by_timestamp[final_timestamp]
    product_pnl: Dict[str, float] = {}
    total_pnl = 0.0
    for product in products:
        mid_price = final_snapshots[product].mid_price
        pnl = cash[product] + position[product] * mid_price
        product_pnl[product] = pnl
        total_pnl += pnl

    return DayResult(
        bot=bot_path.stem,
        family=day_scenario.family,
        sample_id=day_scenario.sample_id,
        day=day_scenario.day,
        total_pnl=round(total_pnl, 4),
        total_fills=total_fills,
        final_positions=dict(position),
        product_pnl={product: round(pnl, 4) for product, pnl in product_pnl.items()},
        block_steps=day_scenario.block_steps,
        passive_fill_prob=round(day_scenario.passive_fill_prob, 6),
        passive_qty_scale=round(day_scenario.passive_qty_scale, 6),
        aggressive_slip_prob=round(day_scenario.aggressive_slip_prob, 6),
        aggressive_slip_ticks=day_scenario.aggressive_slip_ticks,
        path_mode=day_scenario.path_mode,
    )


def flatten_day_result(result: DayResult) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "bot": result.bot,
        "family": result.family,
        "sample_id": result.sample_id,
        "day": result.day,
        "total_pnl": result.total_pnl,
        "total_fills": result.total_fills,
        "path_mode": result.path_mode,
        "block_steps": result.block_steps,
        "passive_fill_prob": result.passive_fill_prob,
        "passive_qty_scale": result.passive_qty_scale,
        "aggressive_slip_prob": result.aggressive_slip_prob,
        "aggressive_slip_ticks": result.aggressive_slip_ticks,
    }
    for product, pnl in sorted(result.product_pnl.items()):
        row[f"{product}_pnl"] = pnl
    for product, position in sorted(result.final_positions.items()):
        row[f"{product}_position"] = position
    return row


def aggregate_samples(day_results: List[DayResult]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    for result in day_results:
        key = (result.bot, result.family, result.sample_id)
        if key not in grouped:
            grouped[key] = {
                "bot": result.bot,
                "family": result.family,
                "sample_id": result.sample_id,
                "total_pnl": 0.0,
                "total_fills": 0,
                "days": {},
                "path_mode": result.path_mode,
                "block_steps": [],
                "passive_fill_prob": [],
                "passive_qty_scale": [],
                "aggressive_slip_prob": [],
                "aggressive_slip_ticks": [],
            }

        entry = grouped[key]
        entry["total_pnl"] += result.total_pnl
        entry["total_fills"] += result.total_fills
        entry["days"][str(result.day)] = result.total_pnl
        entry["block_steps"].append(result.block_steps)
        entry["passive_fill_prob"].append(result.passive_fill_prob)
        entry["passive_qty_scale"].append(result.passive_qty_scale)
        entry["aggressive_slip_prob"].append(result.aggressive_slip_prob)
        entry["aggressive_slip_ticks"].append(result.aggressive_slip_ticks)

    rows: List[Dict[str, Any]] = []
    for (_, _, _), entry in sorted(grouped.items()):
        row = {
            "bot": entry["bot"],
            "family": entry["family"],
            "sample_id": entry["sample_id"],
            "total_pnl": round(entry["total_pnl"], 4),
            "total_fills": entry["total_fills"],
            "path_mode": entry["path_mode"],
            "avg_block_steps": round(statistics.fmean(entry["block_steps"]), 4),
            "avg_passive_fill_prob": round(statistics.fmean(entry["passive_fill_prob"]), 6),
            "avg_passive_qty_scale": round(statistics.fmean(entry["passive_qty_scale"]), 6),
            "avg_aggressive_slip_prob": round(statistics.fmean(entry["aggressive_slip_prob"]), 6),
            "avg_aggressive_slip_ticks": round(statistics.fmean(entry["aggressive_slip_ticks"]), 6),
        }
        for day_key, pnl in sorted(entry["days"].items()):
            row[f"day_{day_key}_pnl"] = round(pnl, 4)
        rows.append(row)

    return rows


def summarize_profiles(sample_rows: List[Dict[str, Any]], bot_name: str) -> Dict[str, Dict[str, float]]:
    profile_summary: Dict[str, Dict[str, float]] = {}
    bot_rows = [row for row in sample_rows if row["bot"] == bot_name]
    for profile_name, families in PROFILE_LIBRARY.items():
        values = [row["total_pnl"] for row in bot_rows if row["family"] in families]
        profile_summary[profile_name] = summarize_distribution(values)
    return profile_summary


def compare_samples(sample_rows: List[Dict[str, Any]], primary_bot: str, compare_bot: str) -> Dict[str, Any]:
    primary_by_key = {
        (row["family"], row["sample_id"]): row["total_pnl"]
        for row in sample_rows
        if row["bot"] == primary_bot
    }
    compare_by_key = {
        (row["family"], row["sample_id"]): row["total_pnl"]
        for row in sample_rows
        if row["bot"] == compare_bot
    }
    shared_keys = sorted(set(primary_by_key) & set(compare_by_key))

    deltas = [primary_by_key[key] - compare_by_key[key] for key in shared_keys]
    family_breakdown: Dict[str, Dict[str, float]] = {}
    for family in sorted({key[0] for key in shared_keys}):
        family_deltas = [primary_by_key[key] - compare_by_key[key] for key in shared_keys if key[0] == family]
        family_breakdown[family] = {
            "samples": len(family_deltas),
            "mean_delta": round(statistics.fmean(family_deltas), 4) if family_deltas else 0.0,
            "win_rate": round(sum(delta > 0 for delta in family_deltas) / len(family_deltas), 4) if family_deltas else 0.0,
            "p10_delta": round(percentile(family_deltas, 0.10), 4) if family_deltas else 0.0,
        }

    return {
        "primary_bot": primary_bot,
        "compare_bot": compare_bot,
        "shared_samples": len(shared_keys),
        "summary": {
            "mean_delta": round(statistics.fmean(deltas), 4) if deltas else 0.0,
            "median_delta": round(percentile(deltas, 0.50), 4) if deltas else 0.0,
            "p10_delta": round(percentile(deltas, 0.10), 4) if deltas else 0.0,
            "win_rate": round(sum(delta > 0 for delta in deltas) / len(deltas), 4) if deltas else 0.0,
        },
        "by_family": family_breakdown,
    }


def compare_profiles(sample_rows: List[Dict[str, Any]], primary_bot: str, compare_bot: str) -> Dict[str, Dict[str, float]]:
    profile_breakdown: Dict[str, Dict[str, float]] = {}
    primary_rows = {
        (row["family"], row["sample_id"]): row["total_pnl"]
        for row in sample_rows
        if row["bot"] == primary_bot
    }
    compare_rows = {
        (row["family"], row["sample_id"]): row["total_pnl"]
        for row in sample_rows
        if row["bot"] == compare_bot
    }
    for profile_name, families in PROFILE_LIBRARY.items():
        shared_keys = sorted(
            key for key in set(primary_rows) & set(compare_rows) if key[0] in families
        )
        deltas = [primary_rows[key] - compare_rows[key] for key in shared_keys]
        profile_breakdown[profile_name] = {
            "samples": len(deltas),
            "mean_delta": round(statistics.fmean(deltas), 4) if deltas else 0.0,
            "median_delta": round(percentile(deltas, 0.50), 4) if deltas else 0.0,
            "p10_delta": round(percentile(deltas, 0.10), 4) if deltas else 0.0,
            "win_rate": round(sum(delta > 0 for delta in deltas) / len(deltas), 4) if deltas else 0.0,
        }
    return profile_breakdown


def build_markdown_report(
    output_prefix: str,
    bot_paths: List[Path],
    families: List[ScenarioFamily],
    baseline_summary: Dict[str, Any],
    monte_carlo_summary: Dict[str, Any],
    comparison: Optional[Dict[str, Any]],
) -> str:
    lines = [
        "# Monte Carlo Robustness Report",
        "",
        f"- Output prefix: `{output_prefix}`",
        f"- Bots: {', '.join(path.name for path in bot_paths)}",
        "",
        "## Families",
        "",
    ]
    for family in families:
        lines.append(f"- `{family.name}`: {family.description}")

    lines.extend(
        [
            "",
            "## Baseline Replay",
            "",
        ]
    )
    for bot_name, summary in sorted(baseline_summary.items()):
        lines.append(f"### {bot_name}")
        lines.append("")
        lines.append(f"- Combined total PnL: `{summary['combined_total_pnl']:.4f}`")
        for day_key, day_total in sorted(summary["per_day"].items()):
            lines.append(f"- Day {day_key}: `{day_total:.4f}`")
        lines.append("")

    lines.extend(
        [
            "## Monte Carlo Summary",
            "",
        ]
    )
    for bot_name, summary in sorted(monte_carlo_summary.items()):
        overall = summary["overall"]
        lines.append(f"### {bot_name}")
        lines.append("")
        lines.append(
            f"- Overall samples: `{overall['count']}` | mean `{overall['mean']}` | "
            f"p10 `{overall['p10']}` | cvar10 `{overall['cvar10']}` | std `{overall['std']}`"
        )
        for profile_name, profile_summary in sorted(summary["profiles"].items()):
            lines.append(
                f"- Profile `{profile_name}`: count `{profile_summary['count']}`, mean `{profile_summary['mean']}`, "
                f"p10 `{profile_summary['p10']}`, cvar10 `{profile_summary['cvar10']}`"
            )
        for family_name, family_summary in sorted(summary["by_family"].items()):
            lines.append(
                f"- `{family_name}`: count `{family_summary['count']}`, mean `{family_summary['mean']}`, "
                f"p10 `{family_summary['p10']}`, cvar10 `{family_summary['cvar10']}`"
            )
        lines.append("")

    if comparison is not None:
        lines.extend(
            [
                "## Comparison",
                "",
                f"- Primary: `{comparison['primary_bot']}`",
                f"- Compare: `{comparison['compare_bot']}`",
                f"- Shared samples: `{comparison['shared_samples']}`",
                f"- Mean delta: `{comparison['summary']['mean_delta']}`",
                f"- Median delta: `{comparison['summary']['median_delta']}`",
                f"- P10 delta: `{comparison['summary']['p10_delta']}`",
                f"- Win rate: `{comparison['summary']['win_rate']}`",
                "",
            ]
        )
        for family_name, family_summary in sorted(comparison["by_family"].items()):
            lines.append(
                f"- `{family_name}`: mean delta `{family_summary['mean_delta']}`, "
                f"p10 delta `{family_summary['p10_delta']}`, win rate `{family_summary['win_rate']}`"
            )
        lines.append("")
        for profile_name, profile_summary in sorted(comparison["by_profile"].items()):
            lines.append(
                f"- Profile `{profile_name}`: mean delta `{profile_summary['mean_delta']}`, "
                f"p10 delta `{profile_summary['p10_delta']}`, win rate `{profile_summary['win_rate']}`"
            )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    families = []
    for family_name in args.families:
        if family_name not in FAMILY_LIBRARY:
            raise ValueError(f"Unknown family: {family_name}")
        families.append(FAMILY_LIBRARY[family_name])

    primary_bot = resolve_bot(args.bot)
    bot_paths = [primary_bot]
    if args.compare_bot:
        compare_bot = resolve_bot(args.compare_bot)
        bot_paths.append(compare_bot)

    ListingClass, ObservationClass, OrderClass, OrderDepthClass, TradeClass, TradingStateClass = RB.ensure_imports(primary_bot)
    datamodel = (ListingClass, ObservationClass, OrderClass, OrderDepthClass, TradeClass, TradingStateClass)
    prices_by_key, market_trades_by_day, listings, ordered_keys = RB.load_market(ListingClass, TradeClass, day_filter=None)

    original_days = {
        day: build_original_day(day, prices_by_key, market_trades_by_day, ordered_keys)
        for day in args.days
    }

    baseline_summary: Dict[str, Any] = {}
    baseline_day_results: List[DayResult] = []
    for bot_path in bot_paths:
        per_day: Dict[int, float] = {}
        combined_total = 0.0
        for day in args.days:
            baseline_scenario = DayScenario(
                family="baseline",
                sample_index=0,
                day=day,
                path_mode="original",
                block_steps=0,
                passive_fill_prob=1.0,
                passive_qty_scale=1.0,
                aggressive_slip_prob=0.0,
                aggressive_slip_ticks=1,
            )
            result = run_replay_day(
                bot_path,
                original_days[day],
                baseline_scenario,
                datamodel,
                listings,
                args.seed,
            )
            baseline_day_results.append(result)
            per_day[day] = result.total_pnl
            combined_total += result.total_pnl
        baseline_summary[bot_path.stem] = {
            "per_day": {str(day): round(total, 4) for day, total in per_day.items()},
            "combined_total_pnl": round(combined_total, 4),
        }

    sampled_scenarios: List[DayScenario] = []
    for family in families:
        for sample_index in range(1, args.samples_per_family + 1):
            for day in args.days:
                sampled_scenarios.append(sample_day_scenario(family, sample_index, day, args.seed))

    replay_days: Dict[Tuple[str, int, str], ReplayDay] = {}
    for day_scenario in sampled_scenarios:
        base_day = original_days[day_scenario.day]
        path_rng = scenario_rng(args.seed + 10_000, day_scenario.family, day_scenario.sample_index, day_scenario.day)
        if day_scenario.path_mode == "bootstrap":
            replay_days[(day_scenario.sample_id, day_scenario.day, day_scenario.family)] = bootstrap_day(
                base_day,
                path_rng,
                day_scenario.block_steps,
                TradeClass,
            )
        else:
            replay_days[(day_scenario.sample_id, day_scenario.day, day_scenario.family)] = base_day

    monte_carlo_day_results: List[DayResult] = []
    for bot_path in bot_paths:
        for day_scenario in sampled_scenarios:
            replay_day = replay_days[(day_scenario.sample_id, day_scenario.day, day_scenario.family)]
            monte_carlo_day_results.append(
                run_replay_day(
                    bot_path,
                    replay_day,
                    day_scenario,
                    datamodel,
                    listings,
                    args.seed,
                )
            )

    sample_rows = aggregate_samples(monte_carlo_day_results)

    monte_carlo_summary: Dict[str, Any] = {}
    for bot_path in bot_paths:
        bot_rows = [row for row in sample_rows if row["bot"] == bot_path.stem]
        overall_values = [row["total_pnl"] for row in bot_rows]
        family_values = {
            family.name: [row["total_pnl"] for row in bot_rows if row["family"] == family.name]
            for family in families
        }
        monte_carlo_summary[bot_path.stem] = {
            "overall": summarize_distribution(overall_values),
            "profiles": summarize_profiles(sample_rows, bot_path.stem),
            "by_family": {
                family_name: summarize_distribution(values)
                for family_name, values in family_values.items()
            },
        }

    comparison = None
    if len(bot_paths) == 2:
        comparison = compare_samples(sample_rows, bot_paths[0].stem, bot_paths[1].stem)
        comparison["by_profile"] = compare_profiles(sample_rows, bot_paths[0].stem, bot_paths[1].stem)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"{args.output_prefix}_report.json"
    markdown_path = OUTPUT_DIR / f"{args.output_prefix}_report.md"
    day_csv_path = OUTPUT_DIR / f"{args.output_prefix}_day_results.csv"
    sample_csv_path = OUTPUT_DIR / f"{args.output_prefix}_sample_totals.csv"

    report_json = {
        "config": {
            "seed": args.seed,
            "days": args.days,
            "samples_per_family": args.samples_per_family,
            "families": [asdict(family) for family in families],
            "bots": [str(path) for path in bot_paths],
        },
        "baseline": baseline_summary,
        "monte_carlo": monte_carlo_summary,
        "comparison": comparison,
    }
    json_path.write_text(json.dumps(report_json, indent=2))
    write_csv(day_csv_path, [flatten_day_result(result) for result in monte_carlo_day_results])
    write_csv(sample_csv_path, sample_rows)
    markdown_path.write_text(
        build_markdown_report(
            args.output_prefix,
            bot_paths,
            families,
            baseline_summary,
            monte_carlo_summary,
            comparison,
        )
    )

    print("Monte Carlo robustness run complete.")
    print(f"Primary bot: {primary_bot}")
    if len(bot_paths) == 2:
        print(f"Compare bot: {bot_paths[1]}")
    print(f"Families: {', '.join(family.name for family in families)}")
    print(f"Samples per family: {args.samples_per_family}")
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    print(f"Wrote {day_csv_path}")
    print(f"Wrote {sample_csv_path}")
    for bot_name, summary in sorted(monte_carlo_summary.items()):
        overall = summary["overall"]
        print(
            f"{bot_name}: mean={overall['mean']:.4f} | p10={overall['p10']:.4f} | "
            f"cvar10={overall['cvar10']:.4f} | std={overall['std']:.4f}"
        )
        for profile_name, profile_summary in sorted(summary["profiles"].items()):
            print(
                f"  profile {profile_name}: mean={profile_summary['mean']:.4f} | "
                f"p10={profile_summary['p10']:.4f} | cvar10={profile_summary['cvar10']:.4f}"
            )
    if comparison is not None:
        print(
            f"{comparison['primary_bot']} vs {comparison['compare_bot']}: "
            f"mean_delta={comparison['summary']['mean_delta']:.4f} | "
            f"win_rate={comparison['summary']['win_rate']:.4f}"
        )
        for profile_name, profile_summary in sorted(comparison["by_profile"].items()):
            print(
                f"  profile {profile_name}: mean_delta={profile_summary['mean_delta']:.4f} | "
                f"p10_delta={profile_summary['p10_delta']:.4f} | win_rate={profile_summary['win_rate']:.4f}"
            )


if __name__ == "__main__":
    main()
