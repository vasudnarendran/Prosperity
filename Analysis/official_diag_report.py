#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize official diagnostic logs from a DIAG-instrumented bot.")
    parser.add_argument("log_path", help="Path to the official .log JSON file")
    parser.add_argument(
        "--output",
        default="",
        help="Optional output directory. Defaults to Analysis/output/<log_stem>_diag/",
    )
    return parser.parse_args()


def load_log(path: Path) -> dict:
    return json.loads(path.read_text())


def parse_activities_log(raw: str) -> Tuple[Dict[Tuple[int, str], dict], Dict[str, List[int]]]:
    snapshots: Dict[Tuple[int, str], dict] = {}
    product_timestamps: Dict[str, List[int]] = defaultdict(list)

    lines = [line for line in raw.splitlines() if line.strip()]
    reader = csv.DictReader(lines, delimiter=";")
    for row in reader:
        timestamp = int(row["timestamp"])
        product = row["product"]
        best_bid = float(row["bid_price_1"]) if row.get("bid_price_1") else None
        best_ask = float(row["ask_price_1"]) if row.get("ask_price_1") else None
        snapshots[(timestamp, product)] = {
            "timestamp": timestamp,
            "product": product,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": float(row["mid_price"]),
            "profit_and_loss": float(row["profit_and_loss"]),
        }
        product_timestamps[product].append(timestamp)

    for product, timestamps in product_timestamps.items():
        product_timestamps[product] = sorted(set(timestamps))

    return snapshots, product_timestamps


def extract_diag_events(log_payload: dict) -> List[dict]:
    events: List[dict] = []
    for row in log_payload.get("logs", []):
        timestamp = int(row.get("timestamp", 0))
        for field in ("lambdaLog", "sandboxLog"):
            text = row.get(field, "") or ""
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith("DIAG "):
                    continue
                try:
                    payload = json.loads(line[5:])
                except json.JSONDecodeError:
                    continue
                for event in payload.get("events", []):
                    item = dict(event)
                    item["_log_timestamp"] = timestamp
                    item["_log_field"] = field
                    events.append(item)
    return events


def build_submission_trade_index(trade_history: List[dict]) -> Dict[Tuple[int, str, str, int], int]:
    index: Dict[Tuple[int, str, str, int], int] = defaultdict(int)
    for trade in trade_history:
        buyer = trade.get("buyer", "") or ""
        seller = trade.get("seller", "") or ""
        if buyer != "SUBMISSION" and seller != "SUBMISSION":
            continue
        side = "BUY" if buyer == "SUBMISSION" else "SELL"
        key = (
            int(trade["timestamp"]),
            str(trade["symbol"]),
            side,
            int(float(trade["price"])),
        )
        index[key] += int(float(trade["quantity"]))
    return index


def markout_for_horizon(
    event: dict,
    snapshots: Dict[Tuple[int, str], dict],
    product_timestamps: Dict[str, List[int]],
    horizon_steps: int,
) -> float | None:
    product = str(event["p"])
    timestamp = int(event["ts"])
    timestamps = product_timestamps.get(product, [])
    if (timestamp, product) not in snapshots or not timestamps:
        return None
    try:
        idx = timestamps.index(timestamp)
    except ValueError:
        return None
    future_idx = idx + horizon_steps
    if future_idx >= len(timestamps):
        return None
    future_timestamp = timestamps[future_idx]
    future_mid = snapshots[(future_timestamp, product)]["mid_price"]
    price = float(event["px"])
    side_sign = 1.0 if event["s"] == "BUY" else -1.0
    return round((future_mid - price) * side_sign, 4)


def event_sort_key(event: dict):
    return (int(event["ts"]), str(event["p"]), str(event["s"]), int(event["px"]))


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    log_path = Path(args.log_path).expanduser().resolve()
    payload = load_log(log_path)

    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (Path(__file__).resolve().parent / "output" / f"{log_path.stem}_diag")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshots, product_timestamps = parse_activities_log(payload.get("activitiesLog", ""))
    submission_trades = build_submission_trade_index(payload.get("tradeHistory", []))
    events = extract_diag_events(payload)
    events = sorted(events, key=event_sort_key)

    enriched_rows: List[dict] = []
    gate_counts: Counter = Counter()
    executed_rows: List[dict] = []

    for event in events:
        timestamp = int(event["ts"])
        product = str(event["p"])
        side = str(event["s"])
        price = int(event["px"])
        snapshot = snapshots.get((timestamp, product), {})
        matched_qty = submission_trades.get((timestamp, product, side, price), 0)

        row = {
            "timestamp": timestamp,
            "product": product,
            "side": side,
            "price": price,
            "threshold": event.get("thr"),
            "threshold_gap": event.get("gap"),
            "edge_mid": event.get("edge_mid"),
            "edge_fair": event.get("edge_fair"),
            "position_before": event.get("pb"),
            "position_after": event.get("pa"),
            "target_position": event.get("tp"),
            "candidate_qty": event.get("cq"),
            "executed_qty": event.get("xq"),
            "matched_trade_qty": matched_qty,
            "risk_reducing": event.get("rr"),
            "aligned_entry": event.get("ae"),
            "crosses_flat": event.get("xf"),
            "gate": event.get("gate"),
            "gate_allowed": event.get("ok"),
            "regime": event.get("regime"),
            "predicted_edge": event.get("pred"),
            "regression_edge": event.get("reg"),
            "fit_quality": event.get("fit"),
            "volatility": event.get("vol"),
            "breakout_score": event.get("breakout"),
            "flow_bias": event.get("flow"),
            "depth_alpha": event.get("depth"),
            "pressure_bias": event.get("pressure"),
            "hybrid_alpha": event.get("hybrid"),
            "channel_position": event.get("cpos"),
            "channel_direction": event.get("cdir"),
            "spread": event.get("spread"),
            "market_trade_count": event.get("mt"),
            "own_trade_count": event.get("ot"),
            "best_bid": snapshot.get("best_bid"),
            "best_ask": snapshot.get("best_ask"),
            "mid_price": snapshot.get("mid_price"),
            "markout_1": markout_for_horizon(event, snapshots, product_timestamps, 1),
            "markout_2": markout_for_horizon(event, snapshots, product_timestamps, 2),
            "markout_4": markout_for_horizon(event, snapshots, product_timestamps, 4),
            "markout_8": markout_for_horizon(event, snapshots, product_timestamps, 8),
        }
        enriched_rows.append(row)
        gate_counts[str(row["gate"])] += 1
        if int(row["executed_qty"] or 0) > 0:
            executed_rows.append(row)

    write_csv(output_dir / "diag_events.csv", enriched_rows)
    (output_dir / "diag_events.json").write_text(json.dumps(enriched_rows, indent=2) + "\n")

    executed_rows_sorted = sorted(
        executed_rows,
        key=lambda row: (
            float(row["edge_mid"]) if row["edge_mid"] is not None else 0.0,
            float(row["markout_1"]) if row["markout_1"] is not None else 0.0,
        ),
    )

    summary_lines = [
        "Official diagnostic summary",
        "==========================",
        f"Log file: {log_path}",
        f"Extracted diagnostic events: {len(enriched_rows)}",
        f"Executed diagnostic events: {len(executed_rows)}",
        "",
        "Gate counts:",
    ]
    for gate, count in gate_counts.most_common():
        summary_lines.append(f"- {gate}: {count}")

    if executed_rows:
        avg_edge_mid = sum(float(row["edge_mid"]) for row in executed_rows if row["edge_mid"] is not None) / len(executed_rows)
        summary_lines.extend(
            [
                "",
                f"Average executed edge vs visible mid: {avg_edge_mid:.4f}",
                "",
                "Worst executed events by visible edge:",
            ]
        )
        for row in executed_rows_sorted[:12]:
            summary_lines.append(
                "- "
                + f"{row['timestamp']} {row['product']} {row['side']} px={row['price']} qty={row['executed_qty']} "
                + f"gate={row['gate']} rr={row['risk_reducing']} xf={row['crosses_flat']} "
                + f"edge_mid={row['edge_mid']} markout1={row['markout_1']} markout4={row['markout_4']}"
            )

    summary_path = output_dir / "summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n")
    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
