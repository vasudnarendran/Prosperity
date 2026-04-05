#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import math
import shutil
import sys
from contextlib import redirect_stdout
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "Data"
BOTS_DIR = ROOT / "Bots"
DEFAULT_BOT = ROOT / "Bots" / "Traderv9.py"
DENOMINATION = "XIRECS"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local Prosperity-style backtest.")
    parser.add_argument(
        "bot",
        nargs="?",
        default="Traderv9.py",
        help="Bot filename or path, for example Traderv9.py or ../Bots/Traderv9.py",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output directory. If omitted, results go to Backtest/output/<bot_name>/",
    )
    parser.add_argument(
        "--day",
        type=int,
        default=-1,
        help="Which day file to run. Default matches the official round-0 site logs: -1",
    )
    return parser.parse_args()


def resolve_bot_path(bot_argument: str) -> Path:
    candidate = Path(bot_argument)
    search_paths = []

    if candidate.is_absolute():
        search_paths.append(candidate)
    else:
        search_paths.extend(
            [
                Path.cwd() / candidate,
                ROOT / "Bots" / candidate,
                ROOT / "Bots" / "archive" / candidate,
            ]
        )

    for path in search_paths:
        if path.exists():
            return path.resolve()

    raise FileNotFoundError(f"Could not find bot file for input: {bot_argument}")


def load_module_from_path(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module {module_name} from {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def ensure_imports(bot_path: Path):
    datamodel_path = BOTS_DIR / "datamodel.py"
    if not datamodel_path.exists():
        raise FileNotFoundError(f"Expected canonical datamodel at {datamodel_path}")

    if str(bot_path.parent) not in sys.path:
        sys.path.insert(0, str(bot_path.parent))
    if str(BOTS_DIR) not in sys.path:
        sys.path.insert(0, str(BOTS_DIR))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    datamodel = load_module_from_path("datamodel", datamodel_path)

    return (
        datamodel.Listing,
        datamodel.Observation,
        datamodel.Order,
        datamodel.OrderDepth,
        datamodel.Trade,
        datamodel.TradingState,
    )


def load_trader(bot_path: Path):
    spec = importlib.util.spec_from_file_location("prosperity_trader_module", bot_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load bot from {bot_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "Trader"):
        raise RuntimeError(f"Bot file {bot_path} does not expose a Trader class")
    return module.Trader()


@dataclass
class Snapshot:
    day: int
    timestamp: int
    abs_timestamp: int
    product: str
    bid_levels: List[Tuple[int, int]]
    ask_levels: List[Tuple[int, int]]
    mid_price: float


@dataclass
class PendingOrder:
    product: str
    side: str
    price: int
    quantity: int
    day: int
    timestamp: int


@dataclass
class Fill:
    day: int
    timestamp: int
    abs_timestamp: int
    product: str
    side: str
    price: int
    quantity: int
    fill_type: str
    source_order_price: int


def parse_price_file(path: Path) -> Dict[Tuple[int, int], Dict[str, Snapshot]]:
    grouped: Dict[Tuple[int, int], Dict[str, Snapshot]] = {}
    with path.open() as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            day = int(row["day"])
            timestamp = int(row["timestamp"])
            abs_timestamp = day * 1_000_000 + timestamp
            product = row["product"]

            bid_levels = []
            ask_levels = []
            for level in ("1", "2", "3"):
                bid_price = row.get(f"bid_price_{level}", "")
                bid_volume = row.get(f"bid_volume_{level}", "")
                ask_price = row.get(f"ask_price_{level}", "")
                ask_volume = row.get(f"ask_volume_{level}", "")

                if bid_price:
                    bid_levels.append((int(float(bid_price)), int(float(bid_volume))))
                if ask_price:
                    ask_levels.append((int(float(ask_price)), abs(int(float(ask_volume)))))

            grouped.setdefault((day, timestamp), {})[product] = Snapshot(
                day=day,
                timestamp=timestamp,
                abs_timestamp=abs_timestamp,
                product=product,
                bid_levels=bid_levels,
                ask_levels=ask_levels,
                mid_price=float(row["mid_price"]),
            )
    return grouped


def parse_trade_file(path: Path, TradeClass) -> Dict[Tuple[int, str], List]:
    trades: Dict[Tuple[int, str], List] = {}
    with path.open() as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            timestamp = int(row["timestamp"])
            product = row["symbol"]
            trade = TradeClass(
                symbol=product,
                price=int(float(row["price"])),
                quantity=int(float(row["quantity"])),
                buyer=row["buyer"] or None,
                seller=row["seller"] or None,
                timestamp=timestamp,
            )
            trades.setdefault((timestamp, product), []).append(trade)
    return trades


def load_market(ListingClass, TradeClass, day_filter: Optional[int] = None):
    prices_by_key: Dict[Tuple[int, int], Dict[str, Snapshot]] = {}
    market_trades_by_day: Dict[int, Dict[Tuple[int, str], List]] = {}

    for price_path in sorted(DATA_DIR.glob("prices_round_0_day_*.csv")):
        day = int(price_path.stem.split("_")[-1])
        if day_filter is not None and day != day_filter:
            continue
        file_prices = parse_price_file(price_path)
        prices_by_key.update(file_prices)

    for trade_path in sorted(DATA_DIR.glob("trades_round_0_day_*.csv")):
        # day is encoded in the filename suffix
        stem = trade_path.stem
        day = int(stem.split("_")[-1])
        if day_filter is not None and day != day_filter:
            continue
        market_trades_by_day[day] = parse_trade_file(trade_path, TradeClass)

    listings = {
        product: ListingClass(symbol=product, product=product, denomination=DENOMINATION)
        for product in sorted({snapshot.product for snapshots in prices_by_key.values() for snapshot in snapshots.values()})
    }
    ordered_keys = sorted(prices_by_key.keys())
    return prices_by_key, market_trades_by_day, listings, ordered_keys


def snapshot_to_order_depth(snapshot: Snapshot, OrderDepthClass):
    order_depth = OrderDepthClass()
    order_depth.buy_orders = {price: volume for price, volume in snapshot.bid_levels}
    order_depth.sell_orders = {price: -volume for price, volume in snapshot.ask_levels}
    return order_depth


def execute_crossing_order(order, snapshot: Snapshot, side: str) -> Tuple[List[Fill], int]:
    remaining = abs(order.quantity)
    fills: List[Fill] = []

    if side == "BUY":
        for ask_price, ask_volume in snapshot.ask_levels:
            if remaining <= 0 or order.price < ask_price:
                break
            fill_qty = min(remaining, ask_volume)
            if fill_qty <= 0:
                continue
            fills.append(
                Fill(
                    day=snapshot.day,
                    timestamp=snapshot.timestamp,
                    abs_timestamp=snapshot.abs_timestamp,
                    product=snapshot.product,
                    side="BUY",
                    price=ask_price,
                    quantity=fill_qty,
                    fill_type="aggressive_cross",
                    source_order_price=order.price,
                )
            )
            remaining -= fill_qty
    else:
        for bid_price, bid_volume in snapshot.bid_levels:
            if remaining <= 0 or order.price > bid_price:
                break
            fill_qty = min(remaining, bid_volume)
            if fill_qty <= 0:
                continue
            fills.append(
                Fill(
                    day=snapshot.day,
                    timestamp=snapshot.timestamp,
                    abs_timestamp=snapshot.abs_timestamp,
                    product=snapshot.product,
                    side="SELL",
                    price=bid_price,
                    quantity=fill_qty,
                    fill_type="aggressive_cross",
                    source_order_price=order.price,
                )
            )
            remaining -= fill_qty

    return fills, remaining


def pending_fill_quantity(order: PendingOrder, snapshot: Snapshot, market_trades: List) -> int:
    if order.side == "BUY":
        crossed_volume = sum(volume for price, volume in snapshot.ask_levels if price <= order.price)
        tape_volume = sum(trade.quantity for trade in market_trades if trade.price <= order.price)
    else:
        crossed_volume = sum(volume for price, volume in snapshot.bid_levels if price >= order.price)
        tape_volume = sum(trade.quantity for trade in market_trades if trade.price >= order.price)

    return max(crossed_volume, tape_volume)


def try_fill_pending_order(order: PendingOrder, snapshot: Snapshot, market_trades: List) -> List[Fill]:
    fillable_quantity = min(order.quantity, pending_fill_quantity(order, snapshot, market_trades))
    if fillable_quantity <= 0:
        return []

    return [
        Fill(
            day=snapshot.day,
            timestamp=snapshot.timestamp,
            abs_timestamp=snapshot.abs_timestamp,
            product=snapshot.product,
            side=order.side,
            price=order.price,
            quantity=fillable_quantity,
            fill_type="passive_resting_fill",
            source_order_price=order.price,
        )
    ]


def apply_fills(fills: List[Fill], cash: Dict[str, float], position: Dict[str, int], TradeClass) -> Dict[str, List]:
    own_trades: Dict[str, List] = defaultdict(list)
    for fill in fills:
        signed_qty = fill.quantity if fill.side == "BUY" else -fill.quantity
        position[fill.product] += signed_qty
        cash[fill.product] -= signed_qty * fill.price
        own_trades[fill.product].append(
            TradeClass(
                symbol=fill.product,
                price=fill.price,
                quantity=fill.quantity,
                buyer="SUBMISSION" if fill.side == "BUY" else None,
                seller="SUBMISSION" if fill.side == "SELL" else None,
                timestamp=fill.timestamp,
            )
        )
    return own_trades


def build_empty_own_trades(products: List[str]) -> Dict[str, List]:
    return {product: [] for product in products}


def build_market_trades(products: List[str], day_trades: Dict[Tuple[int, str], List], timestamp: int) -> Dict[str, List]:
    return {product: list(day_trades.get((timestamp, product), [])) for product in products}


def generate_plots(output_dir: Path, time_points: List[int], total_pnl: List[float], product_history: Dict[str, Dict[str, List[float]]], fills: List[Fill]) -> None:
    plt.style.use("ggplot")

    plt.figure(figsize=(12, 6))
    plt.plot(time_points, total_pnl, label="Total PnL", linewidth=2.0)
    for product, history in sorted(product_history.items()):
        plt.plot(time_points, history["pnl"], label=f"{product} PnL")
    plt.title("PnL Overview")
    plt.xlabel("Abs Timestamp")
    plt.ylabel("PnL")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "pnl_overview.png")
    plt.close()

    plt.figure(figsize=(12, 6))
    for product, history in sorted(product_history.items()):
        plt.plot(time_points, history["position"], label=f"{product} Position")
    plt.title("Positions")
    plt.xlabel("Abs Timestamp")
    plt.ylabel("Position")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "positions.png")
    plt.close()

    fills_by_product: Dict[str, List[Fill]] = defaultdict(list)
    for fill in fills:
        fills_by_product[fill.product].append(fill)

    for product, history in sorted(product_history.items()):
        plt.figure(figsize=(12, 6))
        plt.plot(time_points, history["mid"], label=f"{product} Mid Price", linewidth=1.6)

        buy_x = [fill.abs_timestamp for fill in fills_by_product[product] if fill.side == "BUY"]
        buy_y = [fill.price for fill in fills_by_product[product] if fill.side == "BUY"]
        sell_x = [fill.abs_timestamp for fill in fills_by_product[product] if fill.side == "SELL"]
        sell_y = [fill.price for fill in fills_by_product[product] if fill.side == "SELL"]

        if buy_x:
            plt.scatter(buy_x, buy_y, marker="^", s=22, label="Buys")
        if sell_x:
            plt.scatter(sell_x, sell_y, marker="v", s=22, label="Sells")

        plt.title(f"{product} Price And Fills")
        plt.xlabel("Abs Timestamp")
        plt.ylabel("Price")
        plt.legend()
        plt.tight_layout()
        plt.savefig(output_dir / f"{product.lower()}_price_and_fills.png")
        plt.close()


def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, object]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_orders(orders_by_product: Dict[str, List]) -> str:
    flat = []
    for product, orders in sorted(orders_by_product.items()):
        for order in orders:
            flat.append(f"{product}:{order.price}@{order.quantity}")
    return " | ".join(flat) if flat else "-"


def main() -> None:
    args = parse_args()
    bot_path = resolve_bot_path(args.bot)
    if args.output:
        output_dir = Path(args.output).resolve()
    else:
        output_dir = ROOT / "Backtest" / "output" / bot_path.stem

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ListingClass, ObservationClass, OrderClass, OrderDepthClass, TradeClass, TradingStateClass = ensure_imports(bot_path)
    trader = load_trader(bot_path)

    prices_by_key, market_trades_by_day, listings, ordered_keys = load_market(
        ListingClass,
        TradeClass,
        args.day,
    )
    products = sorted(listings.keys())

    position = {product: 0 for product in products}
    cash = {product: 0.0 for product in products}
    pending_orders: Dict[str, List[PendingOrder]] = {product: [] for product in products}
    last_own_trades = build_empty_own_trades(products)
    trader_data = ""
    current_day: Optional[int] = None

    step_rows: List[Dict[str, object]] = []
    fill_rows: List[Dict[str, object]] = []
    product_rows: List[Dict[str, object]] = []
    fills: List[Fill] = []

    time_points: List[int] = []
    total_pnl_series: List[float] = []
    product_history: Dict[str, Dict[str, List[float]]] = {
        product: {"position": [], "pnl": [], "mid": []} for product in products
    }

    for day, timestamp in ordered_keys:
        if current_day is None:
            current_day = day
        elif day != current_day:
            position = {product: 0 for product in products}
            cash = {product: 0.0 for product in products}
            pending_orders = {product: [] for product in products}
            last_own_trades = build_empty_own_trades(products)
            trader_data = ""
            current_day = day

        snapshots = prices_by_key[(day, timestamp)]
        abs_timestamp = day * 1_000_000 + timestamp
        day_trades = market_trades_by_day.get(day, {})

        fills_between_steps: List[Fill] = []
        for product in products:
            snapshot = snapshots[product]
            market_trades = day_trades.get((timestamp, product), [])
            remaining_pending = []
            for pending in pending_orders[product]:
                new_fills = try_fill_pending_order(pending, snapshot, market_trades)
                if new_fills:
                    fills_between_steps.extend(new_fills)
                    filled_qty = sum(fill.quantity for fill in new_fills)
                    leftover = pending.quantity - filled_qty
                    if leftover > 0:
                        remaining_pending.append(
                            PendingOrder(
                                product=pending.product,
                                side=pending.side,
                                price=pending.price,
                                quantity=leftover,
                                day=pending.day,
                                timestamp=pending.timestamp,
                            )
                        )
                # Resting orders only survive for one interval in this local model.
            pending_orders[product] = []

        if fills_between_steps:
            fills.extend(fills_between_steps)
            last_own_trades = apply_fills(fills_between_steps, cash, position, TradeClass)

        order_depths = {
            product: snapshot_to_order_depth(snapshots[product], OrderDepthClass) for product in products
        }
        market_trades = build_market_trades(products, day_trades, timestamp)
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
            orders_by_product, conversions, trader_data = trader.run(state)
        stdout_text = stdout_buffer.getvalue().strip()

        step_fills: List[Fill] = []
        for product, orders in orders_by_product.items():
            snapshot = snapshots[product]
            for order in orders:
                if not isinstance(order, OrderClass):
                    continue
                if order.quantity == 0:
                    continue

                side = "BUY" if order.quantity > 0 else "SELL"
                aggressive_fills, remaining_qty = execute_crossing_order(order, snapshot, side)
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
                            PendingOrder(
                                product=product,
                                side=side,
                                price=resting_price,
                                quantity=remaining_qty,
                                day=day,
                                timestamp=timestamp,
                            )
                        )

        if step_fills:
            fills.extend(step_fills)
            last_own_trades = apply_fills(step_fills, cash, position, TradeClass)
        else:
            last_own_trades = build_empty_own_trades(products)

        total_pnl = 0.0
        positions_total_abs = 0
        for product in products:
            mid = snapshots[product].mid_price
            unrealized = position[product] * mid
            product_pnl = cash[product] + unrealized
            total_pnl += product_pnl
            positions_total_abs += abs(position[product])

            product_history[product]["position"].append(position[product])
            product_history[product]["pnl"].append(product_pnl)
            product_history[product]["mid"].append(mid)

            product_rows.append(
                {
                    "day": day,
                    "timestamp": timestamp,
                    "abs_timestamp": abs_timestamp,
                    "product": product,
                    "position": position[product],
                    "cash": round(cash[product], 4),
                    "mid_price": mid,
                    "product_pnl": round(product_pnl, 4),
                }
            )

        time_points.append(abs_timestamp)
        total_pnl_series.append(total_pnl)

        step_rows.append(
            {
                "day": day,
                "timestamp": timestamp,
                "abs_timestamp": abs_timestamp,
                "submitted_orders": sum(len(orders) for orders in orders_by_product.values()),
                "executed_fills": len(step_fills),
                "pending_orders_next_step": sum(len(orders) for orders in pending_orders.values()),
                "conversions": conversions,
                "positions_total_abs": positions_total_abs,
                "total_pnl": round(total_pnl, 4),
                "orders": format_orders(orders_by_product),
                "stdout": stdout_text.replace("\n", " | "),
            }
        )

        for fill in step_fills:
            fill_rows.append(
                {
                    "day": fill.day,
                    "timestamp": fill.timestamp,
                    "abs_timestamp": fill.abs_timestamp,
                    "product": fill.product,
                    "side": fill.side,
                    "price": fill.price,
                    "quantity": fill.quantity,
                    "fill_type": fill.fill_type,
                    "source_order_price": fill.source_order_price,
                }
            )

    write_csv(
        output_dir / "step_log.csv",
        [
            "day",
            "timestamp",
            "abs_timestamp",
            "submitted_orders",
            "executed_fills",
            "pending_orders_next_step",
            "conversions",
            "positions_total_abs",
            "total_pnl",
            "orders",
            "stdout",
        ],
        step_rows,
    )
    write_csv(
        output_dir / "fills.csv",
        [
            "day",
            "timestamp",
            "abs_timestamp",
            "product",
            "side",
            "price",
            "quantity",
            "fill_type",
            "source_order_price",
        ],
        fill_rows,
    )
    write_csv(
        output_dir / "product_log.csv",
        ["day", "timestamp", "abs_timestamp", "product", "position", "cash", "mid_price", "product_pnl"],
        product_rows,
    )

    generate_plots(output_dir, time_points, total_pnl_series, product_history, fills)

    summary_lines = [
        "Backtest summary",
        "================",
        f"Bot file: {bot_path}",
        f"Datamodel: {BOTS_DIR / 'datamodel.py'}",
        f"Day filter: {args.day}",
        f"Data sources: {DATA_DIR / f'prices_round_0_day_{args.day}.csv'} and {DATA_DIR / f'trades_round_0_day_{args.day}.csv'}",
        f"Steps: {len(step_rows)}",
        f"Total fills: {len(fill_rows)}",
        f"Final total PnL: {total_pnl_series[-1]:.2f}" if total_pnl_series else "Final total PnL: 0.00",
        f"Best total PnL: {max(total_pnl_series):.2f}" if total_pnl_series else "Best total PnL: 0.00",
        f"Worst total PnL: {min(total_pnl_series):.2f}" if total_pnl_series else "Worst total PnL: 0.00",
        "",
        "Per product final PnL:",
    ]
    for product in products:
        summary_lines.append(
            f"- {product}: {product_history[product]['pnl'][-1]:.2f} | final position {product_history[product]['position'][-1]}"
        )
    summary_lines.extend(
        [
            "",
            "Matching model used here:",
            "- Marketable orders fill immediately against visible book levels.",
            "- Resting orders stay active for one interval and may fill on the next snapshot if the next book or trade tape reaches their price.",
            "- This is a practical local approximation, not the official hidden simulator.",
        ]
    )
    (output_dir / "summary.txt").write_text("\n".join(summary_lines) + "\n")

    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
