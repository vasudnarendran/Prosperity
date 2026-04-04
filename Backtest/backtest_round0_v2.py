from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import contextlib
import io
import sys
import traceback

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

DATA_DIR = WORKSPACE_ROOT / 'Data'
PRICE_FILES = [
    DATA_DIR / 'prices_round_0_day_-2.csv',
    DATA_DIR / 'prices_round_0_day_-1.csv',
]
TRADE_FILES = [
    DATA_DIR / 'trades_round_0_day_-2.csv',
    DATA_DIR / 'trades_round_0_day_-1.csv',
]
OUTPUT_DIR = SCRIPT_DIR / 'backtest_output_v2'
OUTPUT_DIR.mkdir(exist_ok=True)

POSITION_LIMITS = {
    'EMERALDS': 20,
    'TOMATOES': 20,
}

DAY_OFFSET = 1_000_000


@dataclass
class Fill:
    day: int
    timestamp: int
    abs_timestamp: int
    product: str
    side: str
    price: int
    quantity: int
    cash_change: float
    position_after: int


def abs_ts(day: int, timestamp: int) -> int:
    return day * DAY_OFFSET + timestamp


def read_price_data(files: List[Path]) -> pd.DataFrame:
    frames = [pd.read_csv(file, sep=';') for file in files]
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(['day', 'timestamp', 'product']).reset_index(drop=True)
    return df


def read_trade_data(files: List[Path]) -> Dict[Tuple[int, int, str], List[Trade]]:
    trade_map: Dict[Tuple[int, int, str], List[Trade]] = {}
    for file in files:
        day = int(file.stem.split('day_')[-1])
        df = pd.read_csv(file, sep=';')
        for _, row in df.iterrows():
            key = (day, int(row['timestamp']), str(row['symbol']))
            trade_map.setdefault(key, []).append(
                Trade(
                    symbol=str(row['symbol']),
                    price=int(row['price']),
                    quantity=int(row['quantity']),
                    buyer=None if pd.isna(row.get('buyer')) else str(row['buyer']),
                    seller=None if pd.isna(row.get('seller')) else str(row['seller']),
                    timestamp=int(row['timestamp']),
                )
            )
    return trade_map


def to_order_depth(row: pd.Series) -> OrderDepth:
    depth = OrderDepth()
    for level in (1, 2, 3):
        bid_p = row.get(f'bid_price_{level}')
        bid_v = row.get(f'bid_volume_{level}')
        ask_p = row.get(f'ask_price_{level}')
        ask_v = row.get(f'ask_volume_{level}')

        if pd.notna(bid_p) and pd.notna(bid_v):
            depth.buy_orders[int(bid_p)] = int(bid_v)
        if pd.notna(ask_p) and pd.notna(ask_v):
            depth.sell_orders[int(ask_p)] = -int(ask_v)
    return depth


def make_listings(products: List[str]) -> Dict[str, Listing]:
    return {p: Listing(symbol=p, product=p, denomination='XIRECS') for p in products}


def best_bid(depth: OrderDepth) -> int | None:
    return max(depth.buy_orders.keys()) if depth.buy_orders else None


def best_ask(depth: OrderDepth) -> int | None:
    return min(depth.sell_orders.keys()) if depth.sell_orders else None


def execute_crossing_order(
    product: str,
    order: Order,
    depth: OrderDepth,
    positions: Dict[str, int],
    cash: Dict[str, float],
    own_trades: Dict[str, List[Trade]],
    day: int,
    timestamp: int,
) -> List[Fill]:
    fills: List[Fill] = []
    qty = int(order.quantity)
    limit = POSITION_LIMITS.get(product, 20)

    if qty > 0:
        remaining = qty
        for ask in sorted(depth.sell_orders.keys()):
            book_qty = -depth.sell_orders[ask]
            if book_qty <= 0 or ask > order.price or remaining <= 0:
                continue
            capacity = limit - positions[product]
            fill_qty = min(remaining, book_qty, capacity)
            if fill_qty <= 0:
                break

            positions[product] += fill_qty
            cash[product] -= ask * fill_qty
            remaining -= fill_qty
            depth.sell_orders[ask] += fill_qty
            own_trades[product].append(Trade(product, ask, fill_qty, 'SUBMISSION', 'MARKET', timestamp))
            fills.append(Fill(day, timestamp, abs_ts(day, timestamp), product, 'BUY', ask, fill_qty, -ask * fill_qty, positions[product]))

    elif qty < 0:
        remaining = -qty
        for bid in sorted(depth.buy_orders.keys(), reverse=True):
            book_qty = depth.buy_orders[bid]
            if book_qty <= 0 or bid < order.price or remaining <= 0:
                continue
            capacity = limit + positions[product]
            fill_qty = min(remaining, book_qty, capacity)
            if fill_qty <= 0:
                break

            positions[product] -= fill_qty
            cash[product] += bid * fill_qty
            remaining -= fill_qty
            depth.buy_orders[bid] -= fill_qty
            own_trades[product].append(Trade(product, bid, fill_qty, 'MARKET', 'SUBMISSION', timestamp))
            fills.append(Fill(day, timestamp, abs_ts(day, timestamp), product, 'SELL', bid, fill_qty, bid * fill_qty, positions[product]))

    return fills


def run_backtest() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    prices = read_price_data(PRICE_FILES)
    trade_map = read_trade_data(TRADE_FILES)
    products = sorted(prices['product'].unique())
    listings = make_listings(products)

    trader = Trader()
    trader_data = ''
    positions: Dict[str, int] = {p: 0 for p in products}
    cash: Dict[str, float] = {p: 0.0 for p in products}
    own_trades: Dict[str, List[Trade]] = {p: [] for p in products}

    fills_out: List[dict] = []
    product_rows: List[dict] = []
    step_rows: List[dict] = []
    status_rows: List[dict] = []

    grouped = prices.groupby(['day', 'timestamp'], sort=True)

    for (day, timestamp), frame in grouped:
        order_depths: Dict[str, OrderDepth] = {}
        mid_prices: Dict[str, float] = {}
        market_trades: Dict[str, List[Trade]] = {p: [] for p in products}
        snapshot_rows: Dict[str, pd.Series] = {}

        for _, row in frame.iterrows():
            product = str(row['product'])
            snapshot_rows[product] = row
            order_depths[product] = to_order_depth(row)
            mid_prices[product] = float(row['mid_price'])
            market_trades[product] = trade_map.get((int(day), int(timestamp), product), [])

        state = TradingState(
            traderData=trader_data,
            timestamp=int(timestamp),
            listings=listings,
            order_depths=order_depths,
            own_trades={k: list(v) for k, v in own_trades.items()},
            market_trades=market_trades,
            position=dict(positions),
            observations=Observation({}, {}),
        )

        stdout_buffer = io.StringIO()
        result = {p: [] for p in products}
        conversions = 0
        step_error = ''
        try:
            with contextlib.redirect_stdout(stdout_buffer):
                maybe_result = trader.run(state)
            if not isinstance(maybe_result, tuple) or len(maybe_result) != 3:
                raise ValueError('Trader.run must return (result, conversions, traderData).')
            result, conversions, trader_data = maybe_result
        except Exception:
            step_error = traceback.format_exc()
            result = {p: [] for p in products}
            conversions = 0

        trader_stdout = stdout_buffer.getvalue().strip()
        step_fills: List[Fill] = []
        submitted_orders = 0

        for product in products:
            orders = result.get(product, []) if isinstance(result, dict) else []
            for order in orders:
                submitted_orders += 1
                if not isinstance(order, Order):
                    continue
                step_fills.extend(
                    execute_crossing_order(
                        product=product,
                        order=order,
                        depth=order_depths[product],
                        positions=positions,
                        cash=cash,
                        own_trades=own_trades,
                        day=int(day),
                        timestamp=int(timestamp),
                    )
                )

        total_cash = float(sum(cash.values()))
        total_unrealized = float(sum(positions[p] * mid_prices[p] for p in products))
        total_pnl = total_cash + total_unrealized
        current_abs_ts = abs_ts(int(day), int(timestamp))

        for fill in step_fills:
            fills_out.append(fill.__dict__)

        step_rows.append(
            {
                'day': int(day),
                'timestamp': int(timestamp),
                'abs_timestamp': current_abs_ts,
                'submitted_orders': submitted_orders,
                'executed_fills': len(step_fills),
                'conversions': int(conversions),
                'cash_total': total_cash,
                'unrealized_total': total_unrealized,
                'total_pnl': total_pnl,
                'positions_total_abs': int(sum(abs(positions[p]) for p in products)),
                'stdout': trader_stdout,
                'error': step_error,
            }
        )

        for product in products:
            row = snapshot_rows[product]
            depth = order_depths[product]
            prod_fills = [f for f in step_fills if f.product == product]
            executed_qty = sum(f.quantity for f in prod_fills)
            buy_qty = sum(f.quantity for f in prod_fills if f.side == 'BUY')
            sell_qty = sum(f.quantity for f in prod_fills if f.side == 'SELL')
            mtm = cash[product] + positions[product] * mid_prices[product]
            orders_for_product = result.get(product, []) if isinstance(result, dict) else []

            product_rows.append(
                {
                    'day': int(day),
                    'timestamp': int(timestamp),
                    'abs_timestamp': current_abs_ts,
                    'product': product,
                    'best_bid': best_bid(depth),
                    'best_ask': best_ask(depth),
                    'mid_price': mid_prices[product],
                    'bid_price_1': row.get('bid_price_1'),
                    'bid_volume_1': row.get('bid_volume_1'),
                    'ask_price_1': row.get('ask_price_1'),
                    'ask_volume_1': row.get('ask_volume_1'),
                    'position': positions[product],
                    'cash': cash[product],
                    'mtm_pnl': mtm,
                    'submitted_order_count': len(orders_for_product),
                    'submitted_orders': '; '.join(f'{o.price}@{o.quantity}' for o in orders_for_product if isinstance(o, Order)),
                    'fill_count': len(prod_fills),
                    'filled_buy_qty': buy_qty,
                    'filled_sell_qty': sell_qty,
                    'filled_total_qty': executed_qty,
                    'market_trade_count': len(market_trades[product]),
                    'official_profit_and_loss': row.get('profit_and_loss'),
                }
            )

            status = 'ACTIVE'
            if len(orders_for_product) == 0:
                status = 'NO_ORDERS'
            elif len(prod_fills) == 0:
                status = 'NO_FILL'
            if abs(positions[product]) >= POSITION_LIMITS.get(product, 20):
                status = 'AT_LIMIT'

            status_rows.append(
                {
                    'day': int(day),
                    'timestamp': int(timestamp),
                    'abs_timestamp': current_abs_ts,
                    'product': product,
                    'status': status,
                    'position': positions[product],
                    'submitted_order_count': len(orders_for_product),
                    'fill_count': len(prod_fills),
                }
            )

    fills_df = pd.DataFrame(fills_out)
    product_df = pd.DataFrame(product_rows)
    step_df = pd.DataFrame(step_rows)
    status_df = pd.DataFrame(status_rows)

    step_df.to_csv(OUTPUT_DIR / 'step_log.csv', index=False)
    product_df.to_csv(OUTPUT_DIR / 'product_log.csv', index=False)
    fills_df.to_csv(OUTPUT_DIR / 'fills.csv', index=False)
    status_df.to_csv(OUTPUT_DIR / 'status_log.csv', index=False)

    return step_df, product_df, fills_df, status_df


def plot_total_pnl(step_df: pd.DataFrame) -> None:
    plt.figure(figsize=(14, 6))
    plt.plot(step_df['abs_timestamp'], step_df['total_pnl'])
    plt.xlabel('Timestamp')
    plt.ylabel('PnL')
    plt.title('Total PnL over Time')
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'total_pnl.png')
    plt.close()


def plot_price_and_fills(product_df: pd.DataFrame, fills_df: pd.DataFrame, product: str) -> None:
    pdf = product_df[product_df['product'] == product].copy()
    plt.figure(figsize=(14, 6))
    plt.plot(pdf['abs_timestamp'], pdf['mid_price'], label='Mid price')

    if not fills_df.empty:
        fdf = fills_df[fills_df['product'] == product].copy()
        if not fdf.empty:
            buys = fdf[fdf['side'] == 'BUY']
            sells = fdf[fdf['side'] == 'SELL']
            if not buys.empty:
                plt.scatter(buys['abs_timestamp'], buys['price'], marker='^', s=30, label='Buys')
            if not sells.empty:
                plt.scatter(sells['abs_timestamp'], sells['price'], marker='v', s=30, label='Sells')

    plt.xlabel('Timestamp')
    plt.ylabel('Price')
    plt.title(f'{product}: Price and Executed Fills')
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f'{product.lower()}_price_and_fills.png')
    plt.close()


def plot_product_pnl(product_df: pd.DataFrame, product: str) -> None:
    pdf = product_df[product_df['product'] == product].copy()
    plt.figure(figsize=(14, 6))
    plt.plot(pdf['abs_timestamp'], pdf['mtm_pnl'])
    plt.xlabel('Timestamp')
    plt.ylabel('PnL')
    plt.title(f'{product}: Mark-to-Market PnL')
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / f'{product.lower()}_pnl.png')
    plt.close()


def plot_positions(product_df: pd.DataFrame, products: List[str]) -> None:
    plt.figure(figsize=(14, 6))
    for product in products:
        pdf = product_df[product_df['product'] == product].copy()
        plt.plot(pdf['abs_timestamp'], pdf['position'], label=product)
    plt.xlabel('Timestamp')
    plt.ylabel('Position')
    plt.title('Positions by Product')
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'positions.png')
    plt.close()


def write_summary(step_df: pd.DataFrame, product_df: pd.DataFrame, fills_df: pd.DataFrame, status_df: pd.DataFrame) -> None:
    lines: List[str] = []
    lines.append('Backtest summary')
    lines.append('================')
    lines.append(f'Steps: {len(step_df)}')
    lines.append(f'Product rows: {len(product_df)}')
    lines.append(f'Total fills: {len(fills_df)}')
    if not step_df.empty:
        lines.append(f'Final total PnL: {step_df["total_pnl"].iloc[-1]:.2f}')
        lines.append(f'Best total PnL: {step_df["total_pnl"].max():.2f}')
        lines.append(f'Worst total PnL: {step_df["total_pnl"].min():.2f}')
        error_steps = int(step_df['error'].fillna('').ne('').sum())
        lines.append(f'Steps with strategy errors: {error_steps}')

    if not status_df.empty:
        lines.append('')
        lines.append('Status counts by product:')
        counts = status_df.groupby(['product', 'status']).size().reset_index(name='count')
        for _, row in counts.iterrows():
            lines.append(f"- {row['product']} {row['status']}: {int(row['count'])}")

    if not fills_df.empty:
        lines.append('')
        lines.append('Executed fills by product and side:')
        counts = fills_df.groupby(['product', 'side']).size().reset_index(name='count')
        for _, row in counts.iterrows():
            lines.append(f"- {row['product']} {row['side']}: {int(row['count'])}")

    (OUTPUT_DIR / 'summary.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_readme() -> None:
    text = '''# Round 0 Local Backtest v2

## Run

From the folder containing `Trader.py`, `datamodel.py`, and the CSV files:

```bash
python3 backtest_round0_v2.py
```

## What it writes

Everything goes into `backtest_output_v2/`:

- `step_log.csv` – one row per simulator timestamp
- `product_log.csv` – one row per product per timestamp
- `fills.csv` – every executed fill
- `status_log.csv` – tells you whether the bot was active, had no fills, or sat at the position limit
- `total_pnl.png` – the main PnL curve
- `positions.png` – positions over time
- `<product>_price_and_fills.png` – mid price with your buy/sell markers
- `<product>_pnl.png` – per-product mark-to-market PnL
- `summary.txt` – quick overview

## Why this is better than the old version

The old log could look like it stopped because it only gave you a coarse timestamp-level view. This version also writes a product-level log and a status log, so you can see whether the bot:

- still submitted orders
- got no fills
- hit the position limit
- crashed with an exception

## Fill logic

This is still a replay backtest, not the official Prosperity engine.
It fills only when your order crosses the visible best prices in the snapshot.
That makes it useful for debugging and strategy iteration, but not a perfect competition replica.
'''
    (SCRIPT_DIR / 'README_backtest_v2.md').write_text(text, encoding='utf-8')


def main() -> None:
    step_df, product_df, fills_df, status_df = run_backtest()
    products = sorted(product_df['product'].unique()) if not product_df.empty else []

    plot_total_pnl(step_df)
    plot_positions(product_df, products)
    for product in products:
        plot_price_and_fills(product_df, fills_df, product)
        plot_product_pnl(product_df, product)

    write_summary(step_df, product_df, fills_df, status_df)
    write_readme()

    print(f'Saved outputs to: {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
