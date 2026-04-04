from __future__ import annotations

import csv
from pathlib import Path
import sys
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent

import_roots = [WORKSPACE_ROOT]
import_roots.extend(path for path in WORKSPACE_ROOT.iterdir() if path.is_dir())

for import_root in reversed(import_roots):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from example.datamodel import Listing, Observation, Order, OrderDepth, Trade, TradingState
from example.Trader import Trader

DATA_DIR = WORKSPACE_ROOT / "Data"
PRICE_FILES = [
    DATA_DIR / "prices_round_0_day_-2.csv",
    DATA_DIR / "prices_round_0_day_-1.csv",
]
TRADE_FILES = [
    DATA_DIR / "trades_round_0_day_-2.csv",
    DATA_DIR / "trades_round_0_day_-1.csv",
]
OUTPUT_DIR = SCRIPT_DIR / "backtest_output"
OUTPUT_DIR.mkdir(exist_ok=True)

POSITION_LIMITS = {
    "EMERALDS": 20,
    "TOMATOES": 20,
}


def build_market_trade_map(trade_files: List[Path]) -> Dict[Tuple[int, str], List[Trade]]:
    market_trade_map: Dict[Tuple[int, str], List[Trade]] = {}
    for file in trade_files:
        df = pd.read_csv(file, sep=";")
        for _, row in df.iterrows():
            key = (int(row["timestamp"]), str(row["symbol"]))
            market_trade_map.setdefault(key, []).append(
                Trade(
                    symbol=str(row["symbol"]),
                    price=int(row["price"]),
                    quantity=int(row["quantity"]),
                    buyer=None if pd.isna(row.get("buyer")) else str(row["buyer"]),
                    seller=None if pd.isna(row.get("seller")) else str(row["seller"]),
                    timestamp=int(row["timestamp"]),
                )
            )
    return market_trade_map


def load_prices(price_files: List[Path]) -> pd.DataFrame:
    frames = [pd.read_csv(file, sep=";") for file in price_files]
    df = pd.concat(frames, ignore_index=True)
    return df.sort_values(["day", "timestamp", "product"]).reset_index(drop=True)


def make_order_depth(row: pd.Series) -> OrderDepth:
    depth = OrderDepth()

    for level in [1, 2, 3]:
        bid_price = row.get(f"bid_price_{level}")
        bid_volume = row.get(f"bid_volume_{level}")
        ask_price = row.get(f"ask_price_{level}")
        ask_volume = row.get(f"ask_volume_{level}")

        if pd.notna(bid_price) and pd.notna(bid_volume):
            depth.buy_orders[int(bid_price)] = int(bid_volume)
        if pd.notna(ask_price) and pd.notna(ask_volume):
            depth.sell_orders[int(ask_price)] = -int(ask_volume)

    return depth


def simulate() -> pd.DataFrame:
    trader = Trader()
    prices = load_prices(PRICE_FILES)
    market_trade_map = build_market_trade_map(TRADE_FILES)

    listings = {
        "EMERALDS": Listing("EMERALDS", "EMERALDS", "XIRECS"),
        "TOMATOES": Listing("TOMATOES", "TOMATOES", "XIRECS"),
    }

    position: Dict[str, int] = {"EMERALDS": 0, "TOMATOES": 0}
    own_trades_hist: Dict[str, List[Trade]] = {"EMERALDS": [], "TOMATOES": []}
    trader_data = ""
    logs = []

    grouped = prices.groupby(["day", "timestamp"])

    for (day, timestamp), group in grouped:
        order_depths = {}
        mid_prices = {}
        market_trades = {}

        for _, row in group.iterrows():
            product = str(row["product"])
            order_depths[product] = make_order_depth(row)
            mid_prices[product] = float(row["mid_price"])
            market_trades[product] = market_trade_map.get((int(timestamp), product), [])

        state = TradingState(
            traderData=trader_data,
            timestamp=int(timestamp),
            listings=listings,
            order_depths=order_depths,
            own_trades={k: list(v) for k, v in own_trades_hist.items()},
            market_trades=market_trades,
            position=dict(position),
            observations=Observation({}, {}),
        )

        result, conversions, trader_data = trader.run(state)

        realized_pnl_change = 0.0
        executed_orders = []

        for product, orders in result.items():
            depth = order_depths[product]
            limit = POSITION_LIMITS.get(product, 20)

            best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None
            best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None

            for order in orders:
                qty = order.quantity
                if qty == 0:
                    continue

                if qty > 0:
                    if best_ask is not None and order.price >= best_ask:
                        fill_qty = min(qty, -depth.sell_orders[best_ask], limit - position[product])
                        if fill_qty > 0:
                            position[product] += fill_qty
                            trade = Trade(product, best_ask, fill_qty, buyer="SUBMISSION", seller="MARKET", timestamp=int(timestamp))
                            own_trades_hist[product].append(trade)
                            executed_orders.append((product, "BUY", best_ask, fill_qty))
                else:
                    if best_bid is not None and order.price <= best_bid:
                        fill_qty = min(-qty, depth.buy_orders[best_bid], limit + position[product])
                        if fill_qty > 0:
                            position[product] -= fill_qty
                            trade = Trade(product, best_bid, fill_qty, buyer="MARKET", seller="SUBMISSION", timestamp=int(timestamp))
                            own_trades_hist[product].append(trade)
                            executed_orders.append((product, "SELL", best_bid, fill_qty))

        mark_to_market = sum(position[p] * mid_prices[p] for p in position if p in mid_prices)

        logs.append(
            {
                "day": int(day),
                "timestamp": int(timestamp),
                "conversions": int(conversions),
                "position_emeralds": position.get("EMERALDS", 0),
                "position_tomatoes": position.get("TOMATOES", 0),
                "mid_emeralds": mid_prices.get("EMERALDS"),
                "mid_tomatoes": mid_prices.get("TOMATOES"),
                "portfolio_mtm": mark_to_market,
                "executed_orders": str(executed_orders),
            }
        )

    log_df = pd.DataFrame(logs)
    log_df.to_csv(OUTPUT_DIR / "backtest_log.csv", index=False)
    return log_df


def plot_results(log_df: pd.DataFrame) -> None:
    if log_df.empty:
        return

    # portfolio value
    plt.figure(figsize=(10, 5))
    plt.plot(log_df.index, log_df["portfolio_mtm"])
    plt.xlabel("Step")
    plt.ylabel("Portfolio MTM")
    plt.title("Backtest Portfolio MTM")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "portfolio_mtm.png")
    plt.close()

    # positions
    plt.figure(figsize=(10, 5))
    plt.plot(log_df.index, log_df["position_emeralds"], label="EMERALDS")
    plt.plot(log_df.index, log_df["position_tomatoes"], label="TOMATOES")
    plt.xlabel("Step")
    plt.ylabel("Position")
    plt.title("Positions Over Time")
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "positions.png")
    plt.close()


if __name__ == "__main__":
    log_df = simulate()
    plot_results(log_df)
    print(f"Saved logs to: {OUTPUT_DIR / 'backtest_log.csv'}")
    print(f"Saved plot to: {OUTPUT_DIR / 'portfolio_mtm.png'}")
    print(f"Saved plot to: {OUTPUT_DIR / 'positions.png'}")
