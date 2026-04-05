#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "Data"
LOGS_DIR = ROOT / "Bots" / "Logs"
OUTPUT_DIR = ROOT / "Analysis" / "output"


def read_csv(path: Path, delimiter: str = ";") -> List[Dict[str, str]]:
    with path.open() as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def to_float(value: str) -> Optional[float]:
    if value is None or value == "":
        return None
    return float(value)


def to_int(value: str) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(float(value))


def safe_mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def safe_median(values: Iterable[float]) -> float:
    values = list(values)
    return statistics.median(values) if values else 0.0


def safe_stdev(values: Iterable[float]) -> float:
    values = list(values)
    return statistics.pstdev(values) if len(values) > 1 else 0.0


def fmt_float(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def load_price_rows() -> Dict[str, List[Dict[str, Any]]]:
    rows_by_product: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for path in sorted(DATA_DIR.glob("prices_round_0_day_*.csv")):
        for row in read_csv(path):
            product = row["product"]
            parsed = {
                "source": path.name,
                "day": to_int(row["day"]),
                "timestamp": to_int(row["timestamp"]),
                "product": product,
                "bid_price_1": to_int(row["bid_price_1"]),
                "bid_volume_1": to_int(row["bid_volume_1"]) or 0,
                "ask_price_1": to_int(row["ask_price_1"]),
                "ask_volume_1": to_int(row["ask_volume_1"]) or 0,
                "mid_price": to_float(row["mid_price"]) or 0.0,
                "profit_and_loss": to_float(row["profit_and_loss"]) or 0.0,
            }
            rows_by_product[product].append(parsed)
    return rows_by_product


def load_trade_rows() -> Dict[str, List[Dict[str, Any]]]:
    rows_by_product: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for path in sorted(DATA_DIR.glob("trades_round_0_day_*.csv")):
        for row in read_csv(path):
            product = row["symbol"]
            rows_by_product[product].append(
                {
                    "source": path.name,
                    "timestamp": to_int(row["timestamp"]),
                    "buyer": row["buyer"],
                    "seller": row["seller"],
                    "symbol": product,
                    "price": to_float(row["price"]) or 0.0,
                    "quantity": to_int(row["quantity"]) or 0,
                }
            )
    return rows_by_product


def load_bot_logs() -> Dict[str, Dict[str, Any]]:
    logs: Dict[str, Dict[str, Any]] = {}
    for path in sorted(LOGS_DIR.glob("*.log")):
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        activities = list(csv.DictReader(payload["activitiesLog"].splitlines(), delimiter=";"))
        logs[path.stem] = {
            "path": path,
            "activities": activities,
            "trade_history": payload.get("tradeHistory", []),
            "raw": payload,
        }
    return logs


def classify_price_behavior(rows: List[Dict[str, Any]]) -> str:
    mids = [row["mid_price"] for row in rows]
    changes = [mids[i] - mids[i - 1] for i in range(1, len(mids))]
    non_zero_changes = [change for change in changes if abs(change) > 1e-9]
    top_mid_count = Counter(mids).most_common(1)
    dominant_ratio = top_mid_count[0][1] / len(mids) if top_mid_count else 0.0

    reversal_count = 0
    continuation_count = 0
    for i in range(1, len(non_zero_changes)):
        prev = non_zero_changes[i - 1]
        curr = non_zero_changes[i]
        if prev == 0 or curr == 0:
            continue
        if prev * curr < 0:
            reversal_count += 1
        elif prev * curr > 0:
            continuation_count += 1

    if dominant_ratio > 0.70 and reversal_count >= continuation_count:
        return "Looks discretized and strongly mean-reverting around a few anchor levels."
    if continuation_count > reversal_count * 1.2:
        return "Shows persistent directional movement more often than snap-back behavior."
    if reversal_count > continuation_count * 1.2:
        return "Shows short-horizon snap-back behavior more than persistence."
    return "Looks mixed: some directional stretches, but no single behavior dominates."


def build_market_summary(product: str, rows: List[Dict[str, Any]], trades: List[Dict[str, Any]]) -> str:
    mids = [row["mid_price"] for row in rows]
    spreads = [row["ask_price_1"] - row["bid_price_1"] for row in rows if row["ask_price_1"] and row["bid_price_1"]]
    bid_states = Counter((row["bid_price_1"], row["ask_price_1"]) for row in rows if row["bid_price_1"] and row["ask_price_1"])
    mid_states = Counter(mids)

    changes = [mids[i] - mids[i - 1] for i in range(1, len(mids))]
    up_moves = sum(1 for change in changes if change > 0)
    down_moves = sum(1 for change in changes if change < 0)
    flat_moves = sum(1 for change in changes if change == 0)

    reversal_count = 0
    continuation_count = 0
    non_zero = [change for change in changes if change != 0]
    for i in range(1, len(non_zero)):
        if non_zero[i - 1] * non_zero[i] < 0:
            reversal_count += 1
        elif non_zero[i - 1] * non_zero[i] > 0:
            continuation_count += 1

    trade_prices = [trade["price"] for trade in trades]
    trade_sizes = [trade["quantity"] for trade in trades]

    lines = [
        f"# {product}",
        "",
        "Observed Price Behavior",
        f"- Rows: {len(rows)}",
        f"- Mid price range: {fmt_float(min(mids))} to {fmt_float(max(mids))}",
        f"- Mid price mean / stdev: {fmt_float(safe_mean(mids))} / {fmt_float(safe_stdev(mids))}",
        f"- Spread median / max: {fmt_float(safe_median(spreads))} / {fmt_float(max(spreads) if spreads else 0.0)}",
        f"- Top mid states: {', '.join(f'{fmt_float(price)} ({count})' for price, count in mid_states.most_common(5))}",
        f"- Top bid/ask states: {', '.join(f'{bid}/{ask} ({count})' for (bid, ask), count in bid_states.most_common(5))}",
        f"- Move counts: up {up_moves}, down {down_moves}, flat {flat_moves}",
        f"- Reversal vs continuation: {reversal_count} reversals, {continuation_count} continuations",
        f"- Interpretation: {classify_price_behavior(rows)}",
        "",
        "Market Trade Tape",
        f"- Market trades: {len(trades)}",
        f"- Average market trade price: {fmt_float(safe_mean(trade_prices))}",
        f"- Average market trade size: {fmt_float(safe_mean(trade_sizes))}",
    ]
    return "\n".join(lines)


def classify_bot_style(buy_qty: int, sell_qty: int) -> str:
    total = buy_qty + sell_qty
    if total == 0:
        return "inactive"
    if buy_qty == 0 and sell_qty > 0:
        return "one-sided short seller"
    if sell_qty == 0 and buy_qty > 0:
        return "one-sided long buyer"
    imbalance = abs(buy_qty - sell_qty) / total
    if imbalance < 0.20:
        return "two-sided market maker"
    if buy_qty > sell_qty:
        return "net buyer"
    return "net seller"


def classify_fill(
    side: str,
    price: float,
    bid: Optional[float],
    ask: Optional[float],
) -> str:
    if bid is None or ask is None:
        return "unknown"
    if side == "BUY":
        if math.isclose(price, ask, abs_tol=1e-6):
            return "buy_at_best_ask"
        if bid < price < ask:
            return "buy_inside_spread"
    if side == "SELL":
        if math.isclose(price, bid, abs_tol=1e-6):
            return "sell_at_best_bid"
        if bid < price < ask:
            return "sell_inside_spread"
    return "off_book_or_unmatched"


def summarize_log(log_name: str, log_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    activities = log_data["activities"]
    book_lookup: Dict[Tuple[str, int], List[Dict[str, float]]] = defaultdict(list)
    final_pnl_by_product: Dict[str, float] = {}
    for row in activities:
        product = row["product"]
        timestamp = to_int(row["timestamp"]) or 0
        bid = to_float(row["bid_price_1"])
        ask = to_float(row["ask_price_1"])
        book_lookup[(product, timestamp)].append({"bid": bid, "ask": ask})
        final_pnl_by_product[product] = to_float(row["profit_and_loss"]) or 0.0

    summaries: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "pnl": 0.0,
            "buy_count": 0,
            "sell_count": 0,
            "buy_qty": 0,
            "sell_qty": 0,
            "buy_notional": 0.0,
            "sell_notional": 0.0,
            "fills": Counter(),
        }
    )

    for product, pnl in final_pnl_by_product.items():
        summaries[product]["pnl"] = pnl

    for trade in log_data["trade_history"]:
        product = trade["symbol"]
        qty = int(trade["quantity"])
        price = float(trade["price"])
        timestamp = int(trade["timestamp"])

        if trade.get("buyer") == "SUBMISSION":
            side = "BUY"
            summaries[product]["buy_count"] += 1
            summaries[product]["buy_qty"] += qty
            summaries[product]["buy_notional"] += price * qty
        elif trade.get("seller") == "SUBMISSION":
            side = "SELL"
            summaries[product]["sell_count"] += 1
            summaries[product]["sell_qty"] += qty
            summaries[product]["sell_notional"] += price * qty
        else:
            continue

        books = book_lookup.get((product, timestamp), [])
        if books:
            fill_type = classify_fill(side, price, books[0]["bid"], books[0]["ask"])
        else:
            fill_type = "unknown"
        summaries[product]["fills"][fill_type] += 1

    for summary in summaries.values():
        summary["buy_avg"] = summary["buy_notional"] / summary["buy_qty"] if summary["buy_qty"] else None
        summary["sell_avg"] = summary["sell_notional"] / summary["sell_qty"] if summary["sell_qty"] else None
        summary["style"] = classify_bot_style(summary["buy_qty"], summary["sell_qty"])

    return summaries


def build_bot_comparison(log_summaries: Dict[str, Dict[str, Dict[str, Any]]], products: List[str]) -> str:
    total_scores: List[Tuple[str, float]] = []
    for log_name, product_data in log_summaries.items():
        total_scores.append((log_name, sum(info["pnl"] for info in product_data.values())))
    total_scores.sort(key=lambda item: item[1], reverse=True)

    lines = [
        "# Bot Comparison",
        "",
        "Overall Ranking",
    ]
    lines.extend(f"- {name}: {fmt_float(score)}" for name, score in total_scores)

    for product in products:
        ranked = []
        for log_name, product_data in log_summaries.items():
            if product in product_data:
                ranked.append((log_name, product_data[product]["pnl"]))
        ranked.sort(key=lambda item: item[1], reverse=True)

        lines.extend(
            [
                "",
                f"{product} Ranking",
            ]
        )
        lines.extend(f"- {name}: {fmt_float(score)}" for name, score in ranked[:8])

        best_name, best_score = ranked[0]
        worst_name, worst_score = ranked[-1]
        best_style = log_summaries[best_name][product]["style"]
        worst_style = log_summaries[worst_name][product]["style"]
        lines.extend(
            [
                f"- Best: {best_name} ({fmt_float(best_score)}) using {best_style}",
                f"- Worst: {worst_name} ({fmt_float(worst_score)}) using {worst_style}",
            ]
        )

    return "\n".join(lines)


def build_product_bot_report(product: str, product_logs: Dict[str, Dict[str, Any]]) -> str:
    ranked = sorted(product_logs.items(), key=lambda item: item[1]["pnl"], reverse=True)

    lines = [
        f"# {product} Bot Behavior",
        "",
        "Bot Summaries",
    ]
    for log_name, summary in ranked:
        buy_avg = fmt_float(summary["buy_avg"]) if summary["buy_avg"] is not None else "n/a"
        sell_avg = fmt_float(summary["sell_avg"]) if summary["sell_avg"] is not None else "n/a"
        fill_summary = ", ".join(
            f"{name} {count}" for name, count in summary["fills"].most_common(4)
        ) or "no fills"
        lines.extend(
            [
                f"- {log_name}: pnl {fmt_float(summary['pnl'])}, style {summary['style']}",
                f"  buys {summary['buy_count']} trades / {summary['buy_qty']} qty at avg {buy_avg}",
                f"  sells {summary['sell_count']} trades / {summary['sell_qty']} qty at avg {sell_avg}",
                f"  fill profile: {fill_summary}",
            ]
        )

    lines.extend(
        [
            "",
            "Interpretation",
            f"- Best bot for {product}: {ranked[0][0]} with pnl {fmt_float(ranked[0][1]['pnl'])}",
            f"- Weakest bot for {product}: {ranked[-1][0]} with pnl {fmt_float(ranked[-1][1]['pnl'])}",
        ]
    )

    one_sided = [name for name, summary in ranked if "one-sided" in summary["style"]]
    balanced = [name for name, summary in ranked if summary["style"] == "two-sided market maker"]
    if one_sided:
        lines.append(f"- Predictable one-sided behavior showed up in: {', '.join(one_sided)}")
    if balanced:
        lines.append(f"- More balanced two-sided behavior showed up in: {', '.join(balanced[:8])}")

    return "\n".join(lines)


def build_matching_report(log_summaries: Dict[str, Dict[str, Dict[str, Any]]], products: List[str]) -> str:
    totals = Counter()
    per_product: Dict[str, Counter] = defaultdict(Counter)

    for product_data in log_summaries.values():
        for product, summary in product_data.items():
            totals.update(summary["fills"])
            per_product[product].update(summary["fills"])

    lines = [
        "# Matching Inference",
        "",
        "This section is inferred from the recorded fills versus the top-of-book in the logs.",
        "It is not the exchange source code, but it shows how fills behaved in practice.",
        "",
        "All Products",
    ]
    lines.extend(f"- {name}: {count}" for name, count in totals.most_common())

    for product in products:
        lines.extend(["", product])
        lines.extend(f"- {name}: {count}" for name, count in per_product[product].most_common())

    lines.extend(
        [
            "",
            "Reading",
            "- Buy fills at best ask and sell fills at best bid indicate immediate, aggressive executions.",
            "- Inside-spread fills suggest passive quotes getting lifted or hit later.",
            "- If almost all fills are at the touch, the bot is mostly taking liquidity rather than waiting in queue.",
        ]
    )
    return "\n".join(lines)


def build_results_report(log_summaries: Dict[str, Dict[str, Dict[str, Any]]]) -> str:
    total_scores = [
        (log_name, sum(product_info["pnl"] for product_info in product_data.values()))
        for log_name, product_data in log_summaries.items()
    ]
    total_scores.sort(key=lambda item: item[1], reverse=True)

    lines = [
        "# Results Overview",
        "",
        "Best total results from the available bot logs:",
    ]
    lines.extend(f"- {name}: {fmt_float(score)}" for name, score in total_scores[:10])

    if total_scores:
        best_name, best_score = total_scores[0]
        worst_name, worst_score = total_scores[-1]
        lines.extend(
            [
                "",
                "Reading",
                f"- Best recorded run: {best_name} with pnl {fmt_float(best_score)}",
                f"- Weakest recorded run: {worst_name} with pnl {fmt_float(worst_score)}",
                "- Use this file together with the product reports to see whether a new version improved one product by hurting the other.",
                "- The current tool intentionally avoids the old backtest output files and focuses on raw market data plus real bot result logs.",
            ]
        )

    return "\n".join(lines)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    price_rows = load_price_rows()
    trade_rows = load_trade_rows()
    logs = load_bot_logs()
    products = sorted(price_rows.keys())

    log_summaries = {log_name: summarize_log(log_name, log_data) for log_name, log_data in logs.items()}

    write_text(OUTPUT_DIR / "market_overview.txt", "# Market Overview\n")

    for product in products:
        market_report = build_market_summary(product, price_rows[product], trade_rows.get(product, []))
        bot_report = build_product_bot_report(
            product,
            {log_name: summary[product] for log_name, summary in log_summaries.items() if product in summary},
        )
        combined = "\n\n".join([market_report, bot_report])
        write_text(OUTPUT_DIR / f"{product.lower()}_report.txt", combined)

    comparison_report = build_bot_comparison(log_summaries, products)
    matching_report = build_matching_report(log_summaries, products)
    results_report = build_results_report(log_summaries)

    write_text(OUTPUT_DIR / "bot_comparison.txt", comparison_report)
    write_text(OUTPUT_DIR / "matching_report.txt", matching_report)
    write_text(OUTPUT_DIR / "results_report.txt", results_report)
    stale_backtest_report = OUTPUT_DIR / "backtest_report.txt"
    if stale_backtest_report.exists():
        stale_backtest_report.unlink()

    overview_lines = [
        "Analysis finished.",
        "",
        "Generated files:",
    ]
    for path in sorted(OUTPUT_DIR.glob("*.txt")):
        overview_lines.append(f"- {path.relative_to(ROOT)}")
    overview_lines.extend(
        [
            "",
            "Suggested reading order:",
            "- market and bot behavior per product",
            "- bot_comparison.txt",
            "- matching_report.txt",
            "- results_report.txt",
        ]
    )
    overview = "\n".join(overview_lines)
    write_text(OUTPUT_DIR / "README.txt", overview)
    print(overview)


if __name__ == "__main__":
    main()
