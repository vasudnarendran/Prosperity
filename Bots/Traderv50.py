from datamodel import OrderDepth, Order, Trade, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


POSITION_LIMITS: Dict[str, int] = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}

HISTORY_LENGTH = 24
TAKER_FEATURE_DIM = 10
MAKER_FEATURE_DIM = 10

EMERALDS = {
    "ANCHOR": 10000.0,
    "ANCHOR_WEIGHT": 0.82,
    "MID_WEIGHT": 0.18,
    "INVENTORY_SKEW": 0.12,
    "TAKE_TIER_1_DISTANCE": 1.0,
    "TAKE_TIER_2_DISTANCE": 4.0,
    "TAKE_TIER_3_DISTANCE": 8.0,
    "TAKE_TIER_1_SIZE": 6,
    "TAKE_TIER_2_SIZE": 12,
    "TAKE_TIER_3_SIZE": 20,
    "TAKE_IMBALANCE_BONUS": 0.5,
    "CLEAR_WIDTH": 0.0,
    "BASE_ORDER_SIZE": 10,
    "DISREGARD_EDGE": 2.0,
    "JOIN_EDGE": 1.0,
    "DEFAULT_EDGE": 8.0,
    "SOFT_LIMIT_RATIO": 0.25,
}

TOMATOES = {
    "BASE_TAKE_EDGE": 1.00,
    "BASE_QUOTE_EDGE": 2.30,
    "MAX_QUOTE_EDGE": 5.20,
    "PASSIVE_SIZE": 8,
    "MAX_TAKE_SIZE": 10,
    "TIME_HORIZON_TICKS": 10000.0,
    "TOXIC_SPREAD": 15.0,
    "TOXIC_VOL": 3.1,
    "SOFT_LIMIT_BASE": 0.50,
    "SOFT_LIMIT_TREND_BONUS": 0.14,
    "SOFT_LIMIT_TOXIC_PENALTY": 0.14,
    "FEATURE_SCALE_DECAY": 0.94,
    "FEATURE_SCALE_FLOOR": 0.25,
    "TAKER_RLS_LAMBDA": 0.988,
    "TAKER_RLS_DELTA": 6.0,
    "MAKER_RLS_LAMBDA": 0.992,
    "MAKER_RLS_DELTA": 5.0,
    "RLS_SKIP_SPREAD": 16.0,
    "RLS_SKIP_TOXIC": 0.62,
    "FEATURE_CLIP": 3.0,
    "TAKER_TARGET_CLIP": 3.5,
    "MAKER_TARGET_CLIP": 2.5,
    "TAKER_BETA_CLIP": 1.60,
    "MAKER_BETA_CLIP": 1.40,
    "CENTER_ALPHA_WEIGHT": 0.34,
    "REVERSION_ALPHA_WEIGHT": 0.24,
    "REVERSION_BRAKE": 0.25,
    "AS_GAMMA_RANGE": 0.10,
    "AS_GAMMA_TREND": 0.07,
    "AS_GAMMA_TOXIC": 0.18,
    "AS_RESERVATION_SCALE": 0.16,
    "SPREAD_VOL_COEF": 0.74,
    "SPREAD_INV_COEF": 0.34,
    "SPREAD_TOXIC_COEF": 0.78,
    "SPREAD_ADVERSE_COEF": 0.20,
    "SIDE_SCORE_REBATE": 0.22,
    "PASSIVE_MIN_EV": 0.00,
    "PASSIVE_ADVERSE_COEF": 0.45,
    "PASSIVE_MOVE_COST": 0.35,
    "QUEUE_VALUE_COEF": 0.25,
    "FILL_RATE_BLEND_MIN": 25.0,
    "PASSIVE_STATS_DECAY": 0.995,
    "PASSIVE_BUCKET_DECAY": 0.997,
    "PASSIVE_BUCKET_BLEND_MIN": 24.0,
    "PASSIVE_BUCKET_MAX": 48,
    "PASSIVE_BUCKET_MARKOUT_WEIGHT": 0.06,
    "PASSIVE_BUCKET_EDGE_WEIGHT": 0.08,
    "TAKER_MARKOUT_DELAY_TICKS": 300,
    "TAKER_BUCKET_DECAY": 0.996,
    "TAKER_BUCKET_MAX": 36,
    "TAKER_BUCKET_MIN_QTY": 6.0,
    "TAKER_BUCKET_EDGE_WEIGHT": 0.20,
    "TAKE_EV_MARGIN": 0.05,
    "TARGET_BUCKET_WEIGHT": 0.10,
    "POST_FILL_DECAY": 0.72,
    "POST_FILL_MAX_BIAS": 2.0,
    "POST_FILL_QUOTE_PENALTY": 0.18,
    "POST_FILL_TAKE_PENALTY": 0.10,
    "MARKOUT_DELAY_TICKS": 400,
    "MARKOUT_SCALE": 0.22,
    "REGIME_TREND_COEF": 1.35,
    "REGIME_FLOW_COEF": 0.95,
    "REGIME_TOXIC_COEF": 1.15,
    "REGIME_SMOOTH_ALPHA": 0.35,
    "ONE_SIDED_RATIO": 0.42,
    "ONE_SIDED_TOXIC_RATIO": 0.28,
    "ADVERSE_SIDE_ONLY_THRESHOLD": 0.85,
    "RANGE_REDUCE_SELL_URGENCY_EXCESS": 24,
    "RANGE_REDUCE_SELL_CAP": 4,
    "RANGE_REDUCE_SELL_ALPHA_BLOCK": 1.10,
    "RANGE_REDUCE_SELL_FLOW_BLOCK": 0.12,
    "RANGE_REDUCE_SELL_IMBALANCE_BLOCK": 0.12,
    "RANGE_REDUCE_SELL_EXTRA_MARGIN": 0.55,
    "QUOTE_MEMORY_TICKS": 600,
    "MAX_RESTING_QUOTES": 12,
}


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def softmax(logits: Dict[str, float]) -> Dict[str, float]:
    max_logit = max(logits.values())
    exponentials = {key: math.exp(value - max_logit) for key, value in logits.items()}
    total = sum(exponentials.values())
    return {key: value / total for key, value in exponentials.items()}


class OrderBuilder:
    def __init__(self, product: str, position_limit: int, position: int) -> None:
        self.product = product
        self.position_limit = position_limit
        self.position = position
        self.buy_capacity = position_limit - position
        self.sell_capacity = position_limit + position
        self.orders: List[Order] = []

    def projected_position(self) -> int:
        return self.position + sum(order.quantity for order in self.orders)

    def add_buy(self, price: int, quantity: int) -> None:
        quantity = min(max(0, int(quantity)), self.buy_capacity)
        if quantity <= 0:
            return
        self.orders.append(Order(self.product, int(price), quantity))
        self.buy_capacity -= quantity

    def add_sell(self, price: int, quantity: int) -> None:
        quantity = min(max(0, int(quantity)), self.sell_capacity)
        if quantity <= 0:
            return
        self.orders.append(Order(self.product, int(price), -quantity))
        self.sell_capacity -= quantity


class Trader:
    def load_trader_data(self, trader_data: str) -> Tuple[Dict[str, List[float]], Dict[str, Dict[str, object]]]:
        if not trader_data:
            return {}, {}
        try:
            parsed = json.loads(trader_data)
        except json.JSONDecodeError:
            return {}, {}

        history: Dict[str, List[float]] = {}
        raw_history = parsed.get("mid_history", {})
        if isinstance(raw_history, dict):
            for product, values in raw_history.items():
                if isinstance(values, list):
                    history[product] = [float(value) for value in values[-HISTORY_LENGTH:]]

        memory: Dict[str, Dict[str, object]] = {}
        raw_memory = parsed.get("memory", {})
        if isinstance(raw_memory, dict):
            for product, value in raw_memory.items():
                if isinstance(value, dict):
                    memory[product] = value

        return history, memory

    def build_trader_data(
        self,
        mid_history: Dict[str, List[float]],
        memory: Dict[str, Dict[str, object]],
    ) -> str:
        return json.dumps({"mid_history": mid_history, "memory": memory}, separators=(",", ":"))

    def get_book(self, order_depth: OrderDepth, history: List[float]) -> Optional[Dict[str, object]]:
        buy_levels = sorted(order_depth.buy_orders.items(), key=lambda item: item[0], reverse=True)
        sell_levels = sorted(
            ((price, -volume) for price, volume in order_depth.sell_orders.items()),
            key=lambda item: item[0],
        )
        if not buy_levels or not sell_levels:
            return None

        best_bid, best_bid_volume = buy_levels[0]
        best_ask, best_ask_volume = sell_levels[0]
        mid = (best_bid + best_ask) / 2.0
        spread = best_ask - best_bid
        total_top_volume = best_bid_volume + best_ask_volume
        if total_top_volume > 0:
            micro = ((best_bid * best_ask_volume) + (best_ask * best_bid_volume)) / total_top_volume
            l1_imbalance = (best_bid_volume - best_ask_volume) / total_top_volume
        else:
            micro = mid
            l1_imbalance = 0.0

        recent_window = history[-8:] if history else []
        ma20_window = history[-20:] if history else []
        recent_average = sum(recent_window) / len(recent_window) if recent_window else mid
        ma20 = sum(ma20_window) / len(ma20_window) if ma20_window else recent_average
        short_return = mid - history[-1] if history else 0.0

        return {
            "buy_levels": [(int(price), int(volume)) for price, volume in buy_levels[:5]],
            "sell_levels": [(int(price), int(volume)) for price, volume in sell_levels[:5]],
            "best_bid": int(best_bid),
            "best_ask": int(best_ask),
            "best_bid_volume": int(best_bid_volume),
            "best_ask_volume": int(best_ask_volume),
            "mid": float(mid),
            "micro": float(micro),
            "spread": int(spread),
            "l1_imbalance": float(l1_imbalance),
            "recent_average": float(recent_average),
            "ma20": float(ma20),
            "short_return": float(short_return),
        }

    def clamp_inside_spread(
        self,
        book: Dict[str, object],
        buy_quote: Optional[int],
        sell_quote: Optional[int],
    ) -> Tuple[Optional[int], Optional[int]]:
        best_bid = int(book["best_bid"])
        best_ask = int(book["best_ask"])

        final_buy = None
        if buy_quote is not None:
            candidate = max(int(buy_quote), best_bid + 1)
            if candidate < best_ask:
                final_buy = candidate

        final_sell = None
        if sell_quote is not None:
            candidate = min(int(sell_quote), best_ask - 1)
            if candidate > best_bid:
                final_sell = candidate

        return final_buy, final_sell

    def realized_volatility(self, history: List[float], spread: int) -> float:
        if len(history) < 3:
            return max(1.0, spread / 2.0)
        diffs = [abs(history[index] - history[index - 1]) for index in range(1, len(history))]
        recent = diffs[-8:]
        return sum(recent) / max(1, len(recent))

    def current_book_snapshot(self, book: Dict[str, object]) -> Dict[str, List[List[int]]]:
        return {
            "buy": [[price, volume] for price, volume in book["buy_levels"][:5]],
            "sell": [[price, volume] for price, volume in book["sell_levels"][:5]],
        }

    def previous_book_snapshot(self, memory: Dict[str, object]) -> Dict[str, List[List[int]]]:
        raw = memory.get("book")
        if not isinstance(raw, dict):
            return {"buy": [], "sell": []}

        snapshot = {"buy": [], "sell": []}
        for side in ("buy", "sell"):
            values = raw.get(side, [])
            if isinstance(values, list):
                snapshot[side] = [
                    [int(level[0]), int(level[1])]
                    for level in values
                    if isinstance(level, list) and len(level) == 2
                ]
        return snapshot

    def load_vector(self, memory: Dict[str, object], key: str, size: int) -> List[float]:
        raw = memory.get(key)
        if not isinstance(raw, list) or len(raw) != size:
            return [0.0] * size
        return [float(value) if isinstance(value, (int, float)) else 0.0 for value in raw]

    def load_matrix(self, memory: Dict[str, object], key: str, dim: int, delta: float) -> List[List[float]]:
        fallback = [[delta if row == col else 0.0 for col in range(dim)] for row in range(dim)]
        raw = memory.get(key)
        if not isinstance(raw, list) or len(raw) != dim:
            return fallback

        matrix: List[List[float]] = []
        for row, default_row in zip(raw, fallback):
            if not isinstance(row, list) or len(row) != dim:
                matrix.append(default_row[:])
                continue
            matrix.append(
                [
                    float(value) if isinstance(value, (int, float)) else default
                    for value, default in zip(row, default_row)
                ]
            )
        return matrix

    def load_feature_scales(self, memory: Dict[str, object], key: str, dim: int) -> List[float]:
        raw = memory.get(key)
        if not isinstance(raw, list) or len(raw) != dim:
            return [1.0] + [TOMATOES["FEATURE_SCALE_FLOOR"]] * (dim - 1)

        scales = [1.0]
        for value in raw[1:]:
            if isinstance(value, (int, float)):
                scales.append(max(TOMATOES["FEATURE_SCALE_FLOOR"], float(value)))
            else:
                scales.append(TOMATOES["FEATURE_SCALE_FLOOR"])
        return scales

    def load_regime_memory(self, memory: Dict[str, object]) -> Dict[str, float]:
        raw = memory.get("regime")
        if not isinstance(raw, dict):
            return {"trend_up": 0.25, "trend_down": 0.25, "range": 0.40, "toxic": 0.10}
        regime = {}
        for key in ("trend_up", "trend_down", "range", "toxic"):
            regime[key] = max(0.0, float(raw.get(key, 0.0)))
        total = sum(regime.values())
        if total <= 1e-9:
            return {"trend_up": 0.25, "trend_down": 0.25, "range": 0.40, "toxic": 0.10}
        return {key: value / total for key, value in regime.items()}

    def load_passive_stats(self, memory: Dict[str, object]) -> Dict[str, Dict[str, float]]:
        defaults = {
            "BUY": {"posted_qty": 0.0, "filled_qty": 0.0, "markout_ewma": 0.0},
            "SELL": {"posted_qty": 0.0, "filled_qty": 0.0, "markout_ewma": 0.0},
        }
        raw = memory.get("passive_stats")
        if not isinstance(raw, dict):
            return defaults
        result: Dict[str, Dict[str, float]] = {}
        for side in ("BUY", "SELL"):
            side_raw = raw.get(side, {})
            if not isinstance(side_raw, dict):
                result[side] = defaults[side]
                continue
            result[side] = {
                "posted_qty": max(0.0, float(side_raw.get("posted_qty", 0.0))),
                "filled_qty": max(0.0, float(side_raw.get("filled_qty", 0.0))),
                "markout_ewma": float(side_raw.get("markout_ewma", 0.0)),
            }
        return result

    def load_passive_bucket_stats(self, memory: Dict[str, object]) -> Dict[str, Dict[str, float]]:
        raw = memory.get("passive_bucket_stats")
        if not isinstance(raw, dict):
            return {}

        stats: Dict[str, Dict[str, float]] = {}
        for bucket, values in raw.items():
            if not isinstance(bucket, str) or not isinstance(values, dict):
                continue
            posted = max(0.0, float(values.get("posted", 0.0)))
            filled = max(0.0, float(values.get("filled", 0.0)))
            markout = float(values.get("markout", 0.0))
            edge = float(values.get("edge", 0.0))
            if posted <= 1e-9 and filled <= 1e-9 and abs(markout) <= 1e-9 and abs(edge) <= 1e-9:
                continue
            stats[bucket] = {
                "posted": posted,
                "filled": filled,
                "markout": markout,
                "edge": edge,
            }
        return stats

    def decay_passive_stats(self, passive_stats: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
        decay = TOMATOES["PASSIVE_STATS_DECAY"]
        for side in ("BUY", "SELL"):
            passive_stats[side]["posted_qty"] *= decay
            passive_stats[side]["filled_qty"] *= decay
        return passive_stats

    def decay_passive_bucket_stats(self, bucket_stats: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
        decay = TOMATOES["PASSIVE_BUCKET_DECAY"]
        decayed: Dict[str, Dict[str, float]] = {}
        for bucket, values in bucket_stats.items():
            posted = values["posted"] * decay
            filled = values["filled"] * decay
            markout = values["markout"] * decay
            edge = values["edge"] * decay
            if posted + filled + abs(markout) + abs(edge) <= 0.02:
                continue
            decayed[bucket] = {
                "posted": posted,
                "filled": filled,
                "markout": markout,
                "edge": edge,
            }
        if len(decayed) <= TOMATOES["PASSIVE_BUCKET_MAX"]:
            return decayed

        ranked = sorted(
            decayed.items(),
            key=lambda item: item[1]["posted"] + item[1]["filled"] + abs(item[1]["markout"]),
            reverse=True,
        )
        return {bucket: values for bucket, values in ranked[: TOMATOES["PASSIVE_BUCKET_MAX"]]}

    def load_taker_bucket_stats(self, memory: Dict[str, object]) -> Dict[str, Dict[str, float]]:
        raw = memory.get("taker_bucket_stats")
        if not isinstance(raw, dict):
            return {}

        stats: Dict[str, Dict[str, float]] = {}
        for bucket, values in raw.items():
            if not isinstance(bucket, str) or not isinstance(values, dict):
                continue
            qty = max(0.0, float(values.get("qty", 0.0)))
            markout = float(values.get("markout", 0.0))
            if qty <= 1e-9 and abs(markout) <= 1e-9:
                continue
            stats[bucket] = {"qty": qty, "markout": markout}
        return stats

    def decay_taker_bucket_stats(self, bucket_stats: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
        decay = TOMATOES["TAKER_BUCKET_DECAY"]
        decayed: Dict[str, Dict[str, float]] = {}
        for bucket, values in bucket_stats.items():
            qty = values["qty"] * decay
            markout = values["markout"] * decay
            if qty + abs(markout) <= 0.02:
                continue
            decayed[bucket] = {"qty": qty, "markout": markout}

        if len(decayed) <= TOMATOES["TAKER_BUCKET_MAX"]:
            return decayed

        ranked = sorted(
            decayed.items(),
            key=lambda item: item[1]["qty"] + abs(item[1]["markout"]),
            reverse=True,
        )
        return {bucket: values for bucket, values in ranked[: TOMATOES["TAKER_BUCKET_MAX"]]}

    def dominant_regime_bucket(self, regime: Dict[str, float]) -> str:
        if regime["toxic"] >= max(regime["trend_up"], regime["trend_down"], regime["range"]):
            return "T"
        if regime["trend_up"] >= max(regime["trend_down"], regime["range"]):
            return "U"
        if regime["trend_down"] >= regime["range"]:
            return "D"
        return "R"

    def passive_bucket_key(
        self,
        side: str,
        quote: int,
        book: Dict[str, object],
        regime: Dict[str, float],
        position_gap: float,
        soft_limit: int,
    ) -> str:
        best_bid = int(book["best_bid"])
        best_ask = int(book["best_ask"])
        spread = max(1, int(book["spread"]))
        if side == "BUY":
            touch_gap = max(1, best_ask - int(quote))
        else:
            touch_gap = max(1, int(quote) - best_bid)

        if spread <= 12:
            spread_bucket = "s0"
        elif spread <= 14:
            spread_bucket = "s1"
        else:
            spread_bucket = "s2"

        toxic_bucket = "t1" if regime["toxic"] > 0.45 else "t0"
        regime_bucket = self.dominant_regime_bucket(regime)
        inv_ratio = position_gap / max(1, soft_limit)
        if side == "BUY":
            if inv_ratio <= -0.20:
                inv_bucket = "iR"
            elif inv_ratio >= 0.20:
                inv_bucket = "iA"
            else:
                inv_bucket = "iN"
        else:
            if inv_ratio >= 0.20:
                inv_bucket = "iR"
            elif inv_ratio <= -0.20:
                inv_bucket = "iA"
            else:
                inv_bucket = "iN"

        return f"{side}|d{min(4, touch_gap)}|{spread_bucket}|{toxic_bucket}|r{regime_bucket}|{inv_bucket}"

    def taker_bucket_key(
        self,
        side: str,
        taker_alpha: float,
        stretch: float,
        regime: Dict[str, float],
        volatility: float,
    ) -> str:
        alpha_norm = abs(taker_alpha) / max(1.0, volatility)
        if alpha_norm < 0.35:
            alpha_bucket = "a0"
        elif alpha_norm < 0.80:
            alpha_bucket = "a1"
        else:
            alpha_bucket = "a2"

        if abs(stretch) < 0.60:
            stretch_bucket = "x0"
        elif abs(stretch) < 1.50:
            stretch_bucket = "x1"
        else:
            stretch_bucket = "x2"

        return f"{side}|{alpha_bucket}|{stretch_bucket}|r{self.dominant_regime_bucket(regime)}|t{int(regime['toxic'] > 0.45)}"

    def load_resting_quotes(self, memory: Dict[str, object]) -> List[Dict[str, object]]:
        raw = memory.get("resting_quotes")
        if not isinstance(raw, list):
            return []

        quotes: List[Dict[str, object]] = []
        for item in raw[-TOMATOES["MAX_RESTING_QUOTES"] :]:
            if not isinstance(item, dict):
                continue
            features = item.get("features", [])
            if not isinstance(features, list):
                continue
            quotes.append(
                {
                    "side": str(item.get("side", "")),
                    "price": int(item.get("price", 0)),
                    "timestamp": float(item.get("timestamp", 0.0)),
                    "mid": float(item.get("mid", 0.0)),
                    "fill_mid": float(item.get("fill_mid", item.get("mid", 0.0))),
                    "center": float(item.get("center", 0.0)),
                    "bucket": str(item.get("bucket", "")),
                    "qty": max(0, int(item.get("qty", 0))),
                    "filled_qty": max(0, int(item.get("filled_qty", 0))),
                    "features": [float(value) for value in features[:MAKER_FEATURE_DIM]],
                }
            )
        return quotes

    def multi_level_imbalance(self, book: Dict[str, object]) -> float:
        bid_total = 0.0
        ask_total = 0.0
        for index, (_price, volume) in enumerate(book["buy_levels"][:5]):
            bid_total += volume / (index + 1)
        for index, (_price, volume) in enumerate(book["sell_levels"][:5]):
            ask_total += volume / (index + 1)
        total = bid_total + ask_total
        if total <= 1e-9:
            return 0.0
        return (bid_total - ask_total) / total

    def level_flow_features(
        self,
        previous_book: Dict[str, List[List[int]]],
        current_book: Dict[str, List[List[int]]],
    ) -> Tuple[float, float, float, float, float]:
        previous_buy = previous_book.get("buy", [])
        previous_sell = previous_book.get("sell", [])
        current_buy = current_book.get("buy", [])
        current_sell = current_book.get("sell", [])

        flow_features: List[float] = []
        for index in range(3):
            prev_buy_price, prev_buy_volume = previous_buy[index] if index < len(previous_buy) else (None, 0)
            curr_buy_price, curr_buy_volume = current_buy[index] if index < len(current_buy) else (None, 0)
            prev_sell_price, prev_sell_volume = previous_sell[index] if index < len(previous_sell) else (None, 0)
            curr_sell_price, curr_sell_volume = current_sell[index] if index < len(current_sell) else (None, 0)

            buy_delta = 0.0
            if prev_buy_price == curr_buy_price:
                buy_delta = curr_buy_volume - prev_buy_volume
            elif curr_buy_price is not None and (prev_buy_price is None or curr_buy_price > prev_buy_price):
                buy_delta = curr_buy_volume
            elif prev_buy_price is not None:
                buy_delta = -prev_buy_volume

            sell_delta = 0.0
            if prev_sell_price == curr_sell_price:
                sell_delta = curr_sell_volume - prev_sell_volume
            elif curr_sell_price is not None and (prev_sell_price is None or curr_sell_price < prev_sell_price):
                sell_delta = curr_sell_volume
            elif prev_sell_price is not None:
                sell_delta = -prev_sell_volume

            scale = max(18.0, prev_buy_volume + curr_buy_volume + prev_sell_volume + curr_sell_volume)
            flow_features.append((buy_delta - sell_delta) / scale)

        while len(flow_features) < 3:
            flow_features.append(0.0)
        weighted_total = flow_features[0] + 0.60 * flow_features[1] + 0.35 * flow_features[2]
        front_pressure = flow_features[0] - flow_features[2]
        return flow_features[0], flow_features[1], flow_features[2], weighted_total, front_pressure

    def update_scales(self, raw_features: List[float], scales: List[float]) -> Tuple[List[float], List[float]]:
        next_scales: List[float] = [1.0]
        normalized: List[float] = [1.0]
        for index in range(1, len(raw_features)):
            previous_scale = scales[index] if index < len(scales) else TOMATOES["FEATURE_SCALE_FLOOR"]
            target_scale = max(TOMATOES["FEATURE_SCALE_FLOOR"], abs(raw_features[index]))
            current_scale = (
                TOMATOES["FEATURE_SCALE_DECAY"] * previous_scale
                + (1.0 - TOMATOES["FEATURE_SCALE_DECAY"]) * target_scale
            )
            next_scales.append(current_scale)
            normalized.append(clip(raw_features[index] / current_scale, -TOMATOES["FEATURE_CLIP"], TOMATOES["FEATURE_CLIP"]))
        return normalized, next_scales

    def taker_raw_features(
        self,
        book: Dict[str, object],
        ml_imbalance: float,
        flow_features: Tuple[float, float, float, float, float],
        volatility: float,
    ) -> List[float]:
        micro_gap = (float(book["micro"]) - float(book["mid"])) / max(1.0, float(book["spread"]))
        short_return = float(book["short_return"]) / max(1.0, volatility)
        spread_norm = float(book["spread"]) / 16.0
        return [
            1.0,
            clip(micro_gap, -2.0, 2.0),
            clip(float(book["l1_imbalance"]), -1.0, 1.0),
            clip(ml_imbalance, -1.5, 1.5),
            clip(flow_features[0], -2.0, 2.0),
            clip(flow_features[1], -2.0, 2.0),
            clip(flow_features[3], -2.4, 2.4),
            clip(short_return, -3.0, 3.0),
            clip(spread_norm, 0.5, 2.0),
            clip(flow_features[4], -2.4, 2.4),
        ]

    def maker_raw_features(
        self,
        side: str,
        book: Dict[str, object],
        ml_imbalance: float,
        flow_features: Tuple[float, float, float, float, float],
        volatility: float,
        stretch: float,
    ) -> List[float]:
        side_sign = 1.0 if side == "BUY" else -1.0
        micro_gap = (float(book["micro"]) - float(book["mid"])) / max(1.0, float(book["spread"]))
        short_return = float(book["short_return"]) / max(1.0, volatility)
        spread_norm = float(book["spread"]) / 16.0
        return [
            1.0,
            clip(side_sign * micro_gap, -2.0, 2.0),
            clip(side_sign * float(book["l1_imbalance"]), -1.0, 1.0),
            clip(side_sign * ml_imbalance, -1.5, 1.5),
            clip(side_sign * flow_features[0], -2.0, 2.0),
            clip(side_sign * flow_features[3], -2.4, 2.4),
            clip(side_sign * flow_features[4], -2.4, 2.4),
            clip(side_sign * short_return, -3.0, 3.0),
            clip(-side_sign * stretch, -3.0, 3.0),
            clip(spread_norm, 0.5, 2.0),
        ]

    def predict(self, beta: List[float], features: List[float]) -> float:
        return sum(weight * value for weight, value in zip(beta, features))

    def update_model(
        self,
        beta: List[float],
        p_matrix: List[List[float]],
        features: List[float],
        target: float,
        decay: float,
        beta_clip: float,
    ) -> Tuple[List[float], List[List[float]]]:
        dim = len(features)
        p_times_x = [
            sum(p_matrix[row][col] * features[col] for col in range(dim))
            for row in range(dim)
        ]
        denom = decay + sum(features[index] * p_times_x[index] for index in range(dim))
        if abs(denom) <= 1e-9:
            return beta, p_matrix

        gain = [value / denom for value in p_times_x]
        prediction = sum(beta[index] * features[index] for index in range(dim))
        error = target - prediction

        next_beta = [
            clip(beta[index] + gain[index] * error, -beta_clip, beta_clip)
            for index in range(dim)
        ]
        x_t_p = [
            sum(features[row] * p_matrix[row][col] for row in range(dim))
            for col in range(dim)
        ]
        next_matrix: List[List[float]] = []
        for row in range(dim):
            next_row: List[float] = []
            for col in range(dim):
                updated = (p_matrix[row][col] - (gain[row] * x_t_p[col])) / decay
                next_row.append(updated)
            next_matrix.append(next_row)
        return next_beta, next_matrix

    def smooth_regime(
        self,
        current_regime: Dict[str, float],
        previous_regime: Dict[str, float],
    ) -> Dict[str, float]:
        alpha = TOMATOES["REGIME_SMOOTH_ALPHA"]
        prev_up = previous_regime.get("trend_up", 0.0)
        prev_down = previous_regime.get("trend_down", 0.0)
        curr_up = current_regime.get("trend_up", 0.0)
        curr_down = current_regime.get("trend_down", 0.0)
        flipped_direction = (
            (prev_up > prev_down and curr_down > curr_up)
            or (prev_down > prev_up and curr_up > curr_down)
        )
        if flipped_direction:
            alpha = max(0.18, alpha - 0.10)

        blended = {
            key: (1.0 - alpha) * previous_regime.get(key, 0.0) + alpha * current_regime.get(key, 0.0)
            for key in ("trend_up", "trend_down", "range", "toxic")
        }
        total = sum(blended.values())
        if total <= 1e-9:
            return {"trend_up": 0.25, "trend_down": 0.25, "range": 0.40, "toxic": 0.10}
        return {key: value / total for key, value in blended.items()}

    def regime_weights(
        self,
        taker_alpha: float,
        volatility: float,
        spread: int,
        ml_imbalance: float,
        flow_features: Tuple[float, float, float, float, float],
        stretch: float,
        previous_regime: Dict[str, float],
    ) -> Dict[str, float]:
        flow_score = flow_features[3] + 0.35 * flow_features[4]
        trend_signal = taker_alpha / max(1.0, volatility)
        current = softmax(
            {
                "trend_up": (
                    TOMATOES["REGIME_TREND_COEF"] * trend_signal
                    + TOMATOES["REGIME_FLOW_COEF"] * flow_score
                    + 0.30 * ml_imbalance
                ),
                "trend_down": (
                    -TOMATOES["REGIME_TREND_COEF"] * trend_signal
                    - TOMATOES["REGIME_FLOW_COEF"] * flow_score
                    - 0.30 * ml_imbalance
                ),
                "range": 0.55 - 0.80 * abs(trend_signal) - 0.25 * abs(flow_score) - 0.18 * abs(stretch),
                "toxic": (
                    TOMATOES["REGIME_TOXIC_COEF"] * (spread - TOMATOES["TOXIC_SPREAD"]) / 4.0
                    + 0.90 * (volatility - TOMATOES["TOXIC_VOL"])
                    + 0.45 * abs(flow_score)
                ),
            }
        )
        return self.smooth_regime(current, previous_regime)

    def dynamic_soft_limit(self, regime: Dict[str, float], position_limit: int) -> int:
        ratio = (
            TOMATOES["SOFT_LIMIT_BASE"]
            + TOMATOES["SOFT_LIMIT_TREND_BONUS"] * max(regime["trend_up"], regime["trend_down"])
            - TOMATOES["SOFT_LIMIT_TOXIC_PENALTY"] * regime["toxic"]
        )
        return max(14, min(position_limit, int(position_limit * clip(ratio, 0.26, 0.72))))

    def target_position(
        self,
        regime: Dict[str, float],
        taker_alpha: float,
        stretch: float,
        soft_limit: int,
        volatility: float,
        position: int,
        target_markout: float,
    ) -> int:
        trend_component = regime["trend_up"] - regime["trend_down"]
        alpha_component = math.tanh(taker_alpha / max(1.0, volatility))
        reversion_component = -0.35 * clip(stretch, -2.5, 2.5)
        toxic_damp = max(0.25, 1.0 - 0.65 * regime["toxic"])
        target_score = (
            0.60 * trend_component
            + 0.30 * alpha_component
            + 0.22 * reversion_component
        ) * toxic_damp

        if taker_alpha * stretch > 0:
            target_score *= max(0.45, 1.0 - TOMATOES["REVERSION_BRAKE"] * abs(stretch) / 2.5)
        if position * target_score > 0 and abs(position) > 0.60 * soft_limit:
            target_score *= max(0.50, 1.0 - 0.35 * abs(position) / max(1, soft_limit))

        dominant = self.dominant_regime_bucket(regime)
        if dominant in {"U", "D"} and regime["toxic"] < 0.25:
            target_score *= 1.06
        elif dominant == "T":
            target_score *= 0.78
        elif dominant == "R":
            target_score *= 0.94

        target_score *= 1.0 + TOMATOES["TARGET_BUCKET_WEIGHT"] * clip(target_markout, -0.8, 0.8)

        target_score = clip(target_score, -1.0, 1.0)
        return max(-soft_limit, min(soft_limit, round(soft_limit * target_score)))

    def time_fraction_remaining(self, state: TradingState) -> float:
        timestamp = float(getattr(state, "timestamp", 0))
        remaining_ticks = max(0.0, TOMATOES["TIME_HORIZON_TICKS"] - (timestamp / 100.0))
        return remaining_ticks / TOMATOES["TIME_HORIZON_TICKS"]

    def reservation_price(
        self,
        fair_value: float,
        position: int,
        target_position: int,
        volatility: float,
        tau: float,
        regime: Dict[str, float],
    ) -> float:
        if regime["toxic"] >= max(regime["trend_up"], regime["trend_down"], regime["range"]):
            gamma = TOMATOES["AS_GAMMA_TOXIC"]
        elif max(regime["trend_up"], regime["trend_down"]) > regime["range"]:
            gamma = TOMATOES["AS_GAMMA_TREND"]
        else:
            gamma = TOMATOES["AS_GAMMA_RANGE"]
        inventory_gap = position - target_position
        return fair_value - (
            inventory_gap
            * gamma
            * max(0.8, volatility) ** 2
            * max(0.35, tau)
            * TOMATOES["AS_RESERVATION_SCALE"]
        )

    def base_quote_half_spread(
        self,
        book: Dict[str, object],
        position: int,
        target_position: int,
        soft_limit: int,
        volatility: float,
        regime: Dict[str, float],
        buy_bias: float,
        sell_bias: float,
    ) -> float:
        half_spread = max(TOMATOES["BASE_QUOTE_EDGE"], float(book["spread"]) / 3.5)
        half_spread += TOMATOES["SPREAD_VOL_COEF"] * min(3.0, volatility)
        half_spread += TOMATOES["SPREAD_INV_COEF"] * min(1.0, abs(position - target_position) / max(1, soft_limit))
        half_spread += TOMATOES["SPREAD_TOXIC_COEF"] * regime["toxic"]
        half_spread += TOMATOES["SPREAD_ADVERSE_COEF"] * max(buy_bias, sell_bias)
        half_spread += self.quote_width_bucket_adjustment(regime)
        return clip(half_spread, TOMATOES["BASE_QUOTE_EDGE"], TOMATOES["MAX_QUOTE_EDGE"])

    def side_quote_offsets(
        self,
        base_half_spread: float,
        position: int,
        target_position: int,
        soft_limit: int,
        buy_score: float,
        sell_score: float,
        buy_bias: float,
        sell_bias: float,
    ) -> Tuple[float, float]:
        inventory_ratio = clip((position - target_position) / max(1, soft_limit), -1.0, 1.0)
        buy_offset = base_half_spread
        sell_offset = base_half_spread

        buy_offset += 0.35 * max(0.0, inventory_ratio)
        sell_offset += 0.35 * max(0.0, -inventory_ratio)
        buy_offset -= 0.18 * max(0.0, -inventory_ratio)
        sell_offset -= 0.18 * max(0.0, inventory_ratio)

        buy_offset += 0.18 * max(0.0, -buy_score) + 0.18 * buy_bias
        sell_offset += 0.18 * max(0.0, -sell_score) + 0.18 * sell_bias
        buy_offset -= TOMATOES["SIDE_SCORE_REBATE"] * max(0.0, buy_score)
        sell_offset -= TOMATOES["SIDE_SCORE_REBATE"] * max(0.0, sell_score)

        return (
            clip(buy_offset, TOMATOES["BASE_QUOTE_EDGE"], TOMATOES["MAX_QUOTE_EDGE"]),
            clip(sell_offset, TOMATOES["BASE_QUOTE_EDGE"], TOMATOES["MAX_QUOTE_EDGE"]),
        )

    def passive_fill_probability(
        self,
        side: str,
        quote: int,
        book: Dict[str, object],
        regime: Dict[str, float],
        passive_stats: Dict[str, Dict[str, float]],
        passive_bucket_stats: Dict[str, Dict[str, float]],
        position_gap: float,
        soft_limit: int,
    ) -> float:
        best_bid = int(book["best_bid"])
        best_ask = int(book["best_ask"])
        spread = max(1, int(book["spread"]))
        if side == "BUY":
            touch_gap = best_ask - quote
            touch_volume = int(book["best_ask_volume"])
        else:
            touch_gap = quote - best_bid
            touch_volume = int(book["best_bid_volume"])

        distance_factor = 1.0 - ((touch_gap - 1) / max(1.0, spread - 1))
        depth_factor = min(1.0, touch_volume / 18.0)
        model_probability = clip(
            0.06
            + 0.42 * distance_factor
            + 0.12 * depth_factor
            + 0.08 * max(0.0, 1.0 - regime["toxic"]),
            0.05,
            0.88,
        )

        side_stats = passive_stats[side]
        posted_qty = side_stats["posted_qty"]
        side_probability = model_probability
        if posted_qty > 1e-9:
            empirical_fill = clip(side_stats["filled_qty"] / posted_qty, 0.03, 0.95)
            weight = min(0.45, posted_qty / TOMATOES["FILL_RATE_BLEND_MIN"])
            side_probability = (1.0 - weight) * model_probability + weight * empirical_fill

        bucket = self.passive_bucket_key(side, quote, book, regime, position_gap, soft_limit)
        bucket_values = passive_bucket_stats.get(bucket)
        if not bucket_values or bucket_values["posted"] < 8.0:
            return side_probability

        bucket_fill = clip(bucket_values["filled"] / bucket_values["posted"], 0.02, 0.98)
        bucket_weight = min(0.35, bucket_values["posted"] / (2.0 * TOMATOES["PASSIVE_BUCKET_BLEND_MIN"]))
        return (1.0 - bucket_weight) * side_probability + bucket_weight * bucket_fill

    def passive_expected_value(
        self,
        side: str,
        quote: int,
        quote_center: float,
        side_score: float,
        book: Dict[str, object],
        position_gap: float,
        soft_limit: int,
        regime: Dict[str, float],
        adverse_bias: float,
        volatility: float,
        passive_stats: Dict[str, Dict[str, float]],
        passive_bucket_stats: Dict[str, Dict[str, float]],
    ) -> float:
        spread_capture = (quote_center - quote) if side == "BUY" else (quote - quote_center)
        p_fill = self.passive_fill_probability(
            side,
            quote,
            book,
            regime,
            passive_stats,
            passive_bucket_stats,
            position_gap,
            soft_limit,
        )
        bucket = self.passive_bucket_key(side, quote, book, regime, position_gap, soft_limit)
        bucket_values = passive_bucket_stats.get(bucket, {"markout": 0.0, "edge": 0.0})
        if bucket_values.get("filled", 0.0) < 4.0:
            bucket_values = {"markout": 0.0, "edge": 0.0}
        queue_bonus = TOMATOES["QUEUE_VALUE_COEF"] * max(0.0, spread_capture) * max(0.0, 1.0 - regime["toxic"])
        expected_fill_value = (
            spread_capture
            + 0.85 * side_score
            + queue_bonus
            + TOMATOES["PASSIVE_BUCKET_EDGE_WEIGHT"] * max(0.0, bucket_values["edge"])
        )
        empirical_markout = passive_stats[side]["markout_ewma"]
        bucket_markout = bucket_values["markout"]
        adverse_cost = (
            0.12
            + TOMATOES["PASSIVE_ADVERSE_COEF"] * regime["toxic"]
            + TOMATOES["POST_FILL_QUOTE_PENALTY"] * adverse_bias
            + 0.08 * max(0.0, -empirical_markout)
            + TOMATOES["PASSIVE_BUCKET_MARKOUT_WEIGHT"] * max(0.0, -bucket_markout)
        ) * max(0.8, TOMATOES["PASSIVE_MOVE_COST"] * max(1.0, volatility))
        inventory_cost = 0.08 * abs(position_gap) / max(1, soft_limit)
        return (p_fill * expected_fill_value) - adverse_cost - inventory_cost

    def process_matured_taker_trades(
        self,
        state: TradingState,
        pending_taker_trades: List[Dict[str, object]],
        taker_bucket_stats: Dict[str, Dict[str, float]],
        current_mid: float,
    ) -> Tuple[List[Dict[str, object]], Dict[str, Dict[str, float]]]:
        current_ts = float(getattr(state, "timestamp", 0))
        still_pending: List[Dict[str, object]] = []

        for trade in pending_taker_trades:
            age = current_ts - float(trade.get("fill_ts", 0.0))
            if age < TOMATOES["TAKER_MARKOUT_DELAY_TICKS"]:
                still_pending.append(trade)
                continue

            side = str(trade.get("side", ""))
            bucket = str(trade.get("bucket", ""))
            if not bucket:
                continue
            side_sign = 1.0 if side == "BUY" else -1.0
            fill_mid = float(trade.get("fill_mid", current_mid))
            fill_price = float(trade.get("fill_price", fill_mid))
            qty = float(trade.get("qty", 1.0))
            mid_markout = side_sign * (current_mid - fill_mid)
            price_markout = side_sign * (current_mid - fill_price)
            combined_markout = 0.30 * mid_markout + 0.70 * price_markout

            bucket_values = taker_bucket_stats.setdefault(bucket, {"qty": 0.0, "markout": 0.0})
            bucket_values["qty"] += qty
            bucket_values["markout"] = 0.88 * bucket_values["markout"] + 0.12 * combined_markout

        return still_pending, taker_bucket_stats

    def taker_markout_adjustment(
        self,
        side: str,
        taker_alpha: float,
        stretch: float,
        regime: Dict[str, float],
        volatility: float,
        taker_bucket_stats: Dict[str, Dict[str, float]],
    ) -> float:
        bucket = self.taker_bucket_key(side, taker_alpha, stretch, regime, volatility)
        bucket_values = taker_bucket_stats.get(bucket)
        if not bucket_values or bucket_values["qty"] < TOMATOES["TAKER_BUCKET_MIN_QTY"]:
            return 0.0
        return clip(bucket_values["markout"], -1.0, 1.0)

    def quote_width_bucket_adjustment(self, regime: Dict[str, float]) -> float:
        dominant = self.dominant_regime_bucket(regime)
        if dominant == "T":
            return 0.35
        if dominant in {"U", "D"} and regime["toxic"] < 0.25:
            return -0.10
        if dominant == "R" and regime["toxic"] < 0.20:
            return -0.04
        return 0.0

    def take_edge(
        self,
        side: str,
        position: int,
        target_position: int,
        taker_alpha: float,
        stretch: float,
        regime: Dict[str, float],
        adverse_bias: float,
        volatility: float,
        taker_bucket_stats: Dict[str, Dict[str, float]],
    ) -> float:
        edge = TOMATOES["BASE_TAKE_EDGE"]
        edge += 0.20 * regime["toxic"]
        edge += TOMATOES["POST_FILL_TAKE_PENALTY"] * adverse_bias
        edge += 0.08 * min(3.0, volatility)

        position_gap = position - target_position
        if side == "BUY" and position_gap < 0:
            edge -= 0.18
        elif side == "SELL" and position_gap > 0:
            edge -= 0.18

        if side == "BUY" and taker_alpha > 0:
            edge -= min(0.45, 0.14 * taker_alpha)
        elif side == "SELL" and taker_alpha < 0:
            edge -= min(0.45, 0.14 * abs(taker_alpha))

        if side == "BUY" and stretch < 0:
            edge -= min(0.18, 0.06 * abs(stretch))
        elif side == "SELL" and stretch > 0:
            edge -= min(0.18, 0.06 * abs(stretch))

        if side == "BUY" and taker_alpha > 0 and stretch > 0:
            edge += TOMATOES["REVERSION_BRAKE"] * min(0.70, abs(stretch) / 3.0)
        elif side == "SELL" and taker_alpha < 0 and stretch < 0:
            edge += TOMATOES["REVERSION_BRAKE"] * min(0.70, abs(stretch) / 3.0)

        realized_markout = self.taker_markout_adjustment(side, taker_alpha, stretch, regime, volatility, taker_bucket_stats)
        edge -= TOMATOES["TAKER_BUCKET_EDGE_WEIGHT"] * max(0.0, realized_markout)
        edge += TOMATOES["TAKER_BUCKET_EDGE_WEIGHT"] * max(0.0, -realized_markout)
        return max(0.45, edge)

    def aggressive_priority(
        self,
        side: str,
        book: Dict[str, object],
        taker_fair: float,
        edge: float,
    ) -> float:
        if side == "BUY":
            return taker_fair - int(book["best_ask"]) - edge
        return int(book["best_bid"]) - taker_fair - edge

    def aggressive_expected_value(
        self,
        side: str,
        book: Dict[str, object],
        position: int,
        target_position: int,
        soft_limit: int,
        taker_fair: float,
        threshold: float,
    ) -> float:
        levels = book["sell_levels"][:3] if side == "BUY" else book["buy_levels"][:3]
        projected = position
        best_ev = -999.0

        for price, _volume in levels:
            fair_edge = (taker_fair - price) if side == "BUY" else (price - taker_fair)
            inventory_cost = 0.10 * max(0.0, abs(projected - target_position) / max(1, soft_limit) - 0.20)
            net_edge = fair_edge - threshold - inventory_cost
            best_ev = max(best_ev, net_edge)

            if side == "BUY":
                desired = max(0, target_position - projected)
                if desired <= 0 and fair_edge < threshold + 0.70:
                    break
                projected += max(1, desired) if desired > 0 else min(abs(projected), 3)
            else:
                desired = max(0, projected - target_position)
                if desired <= 0 and fair_edge < threshold + 0.70:
                    break
                projected -= max(1, desired) if desired > 0 else min(max(0, projected), 3)

            if net_edge <= 0:
                break

        return best_ev

    def range_reducing_sell_control(
        self,
        regime: Dict[str, float],
        position: int,
        target_position: int,
        soft_limit: int,
        taker_alpha: float,
        flow_score: float,
        ml_imbalance: float,
        fair_edge: float,
        threshold: float,
    ) -> Tuple[bool, Optional[int]]:
        desired = max(0, position - target_position)
        if desired <= 0 or self.dominant_regime_bucket(regime) != "R":
            return True, None

        if desired >= TOMATOES["RANGE_REDUCE_SELL_URGENCY_EXCESS"] or abs(position) >= soft_limit:
            return True, None

        bullish_pressure = (
            taker_alpha >= TOMATOES["RANGE_REDUCE_SELL_ALPHA_BLOCK"]
            or flow_score >= TOMATOES["RANGE_REDUCE_SELL_FLOW_BLOCK"]
            or ml_imbalance >= TOMATOES["RANGE_REDUCE_SELL_IMBALANCE_BLOCK"]
        )
        if not bullish_pressure:
            return True, None

        if fair_edge < threshold + TOMATOES["RANGE_REDUCE_SELL_EXTRA_MARGIN"]:
            return False, None

        return True, int(TOMATOES["RANGE_REDUCE_SELL_CAP"])

    def sweep_book(
        self,
        side: str,
        book: Dict[str, object],
        builder: OrderBuilder,
        taker_fair: float,
        threshold: float,
        target_position: int,
        soft_limit: int,
        current_ts: float,
        current_mid: float,
        taker_bucket: str,
        pending_taker_trades: List[Dict[str, object]],
        regime: Dict[str, float],
        taker_alpha: float,
        flow_score: float,
        ml_imbalance: float,
    ) -> bool:
        traded = False
        levels = book["sell_levels"][:3] if side == "BUY" else book["buy_levels"][:3]
        for price, volume in levels:
            projected = builder.projected_position()
            fair_edge = (taker_fair - price) if side == "BUY" else (price - taker_fair)
            inventory_cost = 0.10 * max(0.0, abs(projected - target_position) / max(1, soft_limit) - 0.20)
            net_edge = fair_edge - threshold - inventory_cost
            if net_edge <= 0:
                break

            if side == "BUY":
                desired = max(0, target_position - projected)
                if desired <= 0 and fair_edge < threshold + 0.70:
                    break
                quantity = min(volume, builder.buy_capacity, TOMATOES["MAX_TAKE_SIZE"])
                if desired > 0:
                    quantity = min(quantity, max(1, desired))
                else:
                    quantity = min(quantity, max(1, min(abs(projected), 3)))
                if quantity <= 0:
                    continue
                builder.add_buy(price, quantity)
                pending_taker_trades.append(
                    {
                        "side": "BUY",
                        "fill_ts": current_ts,
                        "fill_mid": current_mid,
                        "fill_price": float(price),
                        "qty": float(quantity),
                        "bucket": taker_bucket,
                    }
                )
                traded = True
            else:
                desired = max(0, projected - target_position)
                if desired <= 0 and fair_edge < threshold + 0.70:
                    break
                reduce_allowed, reduce_cap = self.range_reducing_sell_control(
                    regime,
                    projected,
                    target_position,
                    soft_limit,
                    taker_alpha,
                    flow_score,
                    ml_imbalance,
                    fair_edge,
                    threshold,
                )
                if not reduce_allowed:
                    break
                quantity = min(volume, builder.sell_capacity, TOMATOES["MAX_TAKE_SIZE"])
                if desired > 0:
                    quantity = min(quantity, max(1, desired))
                    if reduce_cap is not None:
                        quantity = min(quantity, reduce_cap)
                else:
                    quantity = min(quantity, max(1, min(projected, 3)))
                if quantity <= 0:
                    continue
                builder.add_sell(price, quantity)
                pending_taker_trades.append(
                    {
                        "side": "SELL",
                        "fill_ts": current_ts,
                        "fill_mid": current_mid,
                        "fill_price": float(price),
                        "qty": float(quantity),
                        "bucket": taker_bucket,
                    }
                )
                traded = True
        return traded

    def attribute_passive_fills(
        self,
        state: TradingState,
        product: str,
        resting_quotes: List[Dict[str, object]],
        last_fill_ts: int,
        passive_stats: Dict[str, Dict[str, float]],
        passive_bucket_stats: Dict[str, Dict[str, float]],
        current_mid: float,
    ) -> Tuple[int, List[Dict[str, object]], List[Dict[str, object]]]:
        new_pending: List[Dict[str, object]] = []
        quotes = [quote.copy() for quote in resting_quotes]
        old_last_fill_ts = last_fill_ts
        max_seen_ts = last_fill_ts

        for trade in state.own_trades.get(product, []):
            if not isinstance(trade, Trade):
                continue
            trade_ts = int(getattr(trade, "timestamp", -1))
            if trade_ts < old_last_fill_ts:
                continue
            max_seen_ts = max(max_seen_ts, trade_ts)

            side = None
            if getattr(trade, "buyer", None) == "SUBMISSION":
                side = "BUY"
            elif getattr(trade, "seller", None) == "SUBMISSION":
                side = "SELL"
            if side is None:
                continue

            price = int(getattr(trade, "price", 0))
            qty = max(1, abs(int(getattr(trade, "quantity", 0))))
            remaining_trade_qty = qty
            for quote in reversed(quotes):
                if remaining_trade_qty <= 0:
                    break
                if quote["side"] != side or quote["price"] != price:
                    continue
                if trade_ts < quote["timestamp"] or trade_ts - quote["timestamp"] > TOMATOES["QUOTE_MEMORY_TICKS"]:
                    continue
                remaining_quote_qty = int(quote["qty"]) - int(quote["filled_qty"])
                if remaining_quote_qty <= 0:
                    continue

                matched_qty = min(remaining_trade_qty, remaining_quote_qty)
                quote["filled_qty"] = int(quote["filled_qty"]) + matched_qty
                passive_stats[side]["filled_qty"] += matched_qty
                bucket = str(quote.get("bucket", ""))
                if bucket:
                    bucket_values = passive_bucket_stats.setdefault(
                        bucket,
                        {"posted": 0.0, "filled": 0.0, "markout": 0.0, "edge": 0.0},
                    )
                    bucket_values["filled"] += matched_qty
                new_pending.append(
                    {
                        "side": side,
                        "quote_ts": float(quote["timestamp"]),
                        "fill_ts": float(trade_ts),
                        "quote_mid": float(quote["mid"]),
                        "fill_mid": current_mid,
                        "fill_price": float(price),
                        "qty": float(matched_qty),
                        "bucket": bucket,
                        "features": quote["features"],
                    }
                )
                remaining_trade_qty -= matched_qty

        trimmed_quotes: List[Dict[str, object]] = []
        current_ts = float(getattr(state, "timestamp", 0))
        for quote in quotes:
            if current_ts - float(quote["timestamp"]) > TOMATOES["QUOTE_MEMORY_TICKS"]:
                continue
            if int(quote["filled_qty"]) >= int(quote["qty"]):
                continue
            trimmed_quotes.append(quote)
        return max_seen_ts, trimmed_quotes[-TOMATOES["MAX_RESTING_QUOTES"] :], new_pending

    def process_matured_passive_fills(
        self,
        state: TradingState,
        pending_fills: List[Dict[str, object]],
        maker_beta: List[float],
        maker_p_matrix: List[List[float]],
        passive_stats: Dict[str, Dict[str, float]],
        passive_bucket_stats: Dict[str, Dict[str, float]],
        current_mid: float,
        volatility: float,
        buy_bias: float,
        sell_bias: float,
        spread: float,
        toxic_score: float,
    ) -> Tuple[
        List[Dict[str, object]],
        List[float],
        List[List[float]],
        Dict[str, Dict[str, float]],
        Dict[str, Dict[str, float]],
        float,
        float,
    ]:
        current_ts = float(getattr(state, "timestamp", 0))
        still_pending: List[Dict[str, object]] = []

        for fill in pending_fills:
            age = current_ts - float(fill.get("fill_ts", 0.0))
            if age < TOMATOES["MARKOUT_DELAY_TICKS"]:
                still_pending.append(fill)
                continue

            side = str(fill.get("side", ""))
            side_sign = 1.0 if side == "BUY" else -1.0
            fill_mid = float(fill.get("fill_mid", current_mid))
            fill_price = float(fill.get("fill_price", fill_mid))
            qty = float(fill.get("qty", 1.0))
            bucket = str(fill.get("bucket", ""))
            features = fill.get("features", [])
            if not isinstance(features, list) or len(features) != MAKER_FEATURE_DIM:
                features = [0.0] * MAKER_FEATURE_DIM

            mid_markout = side_sign * (current_mid - fill_mid)
            price_markout = side_sign * (current_mid - fill_price)
            combined_markout = 0.35 * mid_markout + 0.65 * price_markout
            fill_edge = side_sign * (fill_mid - fill_price)
            clipped_target = clip(combined_markout, -TOMATOES["MAKER_TARGET_CLIP"], TOMATOES["MAKER_TARGET_CLIP"])
            if spread < TOMATOES["RLS_SKIP_SPREAD"] and toxic_score < TOMATOES["RLS_SKIP_TOXIC"]:
                maker_beta, maker_p_matrix = self.update_model(
                    maker_beta,
                    maker_p_matrix,
                    [float(value) for value in features],
                    clipped_target,
                    TOMATOES["MAKER_RLS_LAMBDA"],
                    TOMATOES["MAKER_BETA_CLIP"],
                )

            passive_stats[side]["markout_ewma"] = (
                0.85 * passive_stats[side]["markout_ewma"] + 0.15 * combined_markout
            )
            if bucket:
                bucket_values = passive_bucket_stats.setdefault(
                    bucket,
                    {"posted": 0.0, "filled": 0.0, "markout": 0.0, "edge": 0.0},
                )
                bucket_values["markout"] = 0.88 * bucket_values["markout"] + 0.12 * combined_markout
                bucket_values["edge"] = 0.88 * bucket_values["edge"] + 0.12 * fill_edge
            step = min(
                TOMATOES["POST_FILL_MAX_BIAS"],
                0.05 * qty + TOMATOES["MARKOUT_SCALE"] * min(3.0, abs(combined_markout) / max(1.0, volatility)),
            )
            if side == "BUY":
                if combined_markout < 0:
                    buy_bias = min(TOMATOES["POST_FILL_MAX_BIAS"], buy_bias + step)
                else:
                    buy_bias = max(0.0, buy_bias - 0.50 * step)
            elif side == "SELL":
                if combined_markout < 0:
                    sell_bias = min(TOMATOES["POST_FILL_MAX_BIAS"], sell_bias + step)
                else:
                    sell_bias = max(0.0, sell_bias - 0.50 * step)

        return still_pending, maker_beta, maker_p_matrix, passive_stats, passive_bucket_stats, buy_bias, sell_bias

    def maker_scores(
        self,
        maker_beta: List[float],
        buy_features: List[float],
        sell_features: List[float],
    ) -> Tuple[float, float]:
        buy_score = clip(self.predict(maker_beta, buy_features), -2.5, 2.5)
        sell_score = clip(self.predict(maker_beta, sell_features), -2.5, 2.5)
        return buy_score, sell_score

    def should_allow_passive_side(
        self,
        side: str,
        position: int,
        target_position: int,
        soft_limit: int,
        regime: Dict[str, float],
        buy_ev: float,
        sell_ev: float,
        buy_score: float,
        sell_score: float,
        buy_bias: float,
        sell_bias: float,
    ) -> bool:
        inventory_gap = position - target_position
        inventory_ratio = abs(inventory_gap) / max(1, soft_limit)
        reducing_side = None
        if inventory_gap > 0:
            reducing_side = "SELL"
        elif inventory_gap < 0:
            reducing_side = "BUY"

        if reducing_side is None:
            if side == "BUY" and buy_bias >= TOMATOES["ADVERSE_SIDE_ONLY_THRESHOLD"] and regime["toxic"] > 0.40:
                return False
            if side == "SELL" and sell_bias >= TOMATOES["ADVERSE_SIDE_ONLY_THRESHOLD"] and regime["toxic"] > 0.40:
                return False
            return True

        if regime["toxic"] > 0.45 and inventory_ratio >= TOMATOES["ONE_SIDED_TOXIC_RATIO"]:
            return side == reducing_side

        if inventory_ratio >= TOMATOES["ONE_SIDED_RATIO"]:
            if side == reducing_side:
                return True
            if side == "BUY":
                return buy_ev > sell_ev + 0.18 and buy_score > 0.20 and buy_bias < TOMATOES["ADVERSE_SIDE_ONLY_THRESHOLD"]
            return sell_ev > buy_ev + 0.18 and sell_score > 0.20 and sell_bias < TOMATOES["ADVERSE_SIDE_ONLY_THRESHOLD"]

        if side == "BUY" and buy_bias >= TOMATOES["ADVERSE_SIDE_ONLY_THRESHOLD"] and inventory_gap >= 0:
            return False
        if side == "SELL" and sell_bias >= TOMATOES["ADVERSE_SIDE_ONLY_THRESHOLD"] and inventory_gap <= 0:
            return False
        return True

    def trade_emeralds(
        self,
        state: TradingState,
        product: str,
        history: Dict[str, List[float]],
    ) -> List[Order]:
        book = self.get_book(state.order_depths[product], history.get(product, []))
        if book is None:
            return []

        product_history = history.get(product, [])
        product_history.append(float(book["mid"]))
        history[product] = product_history[-HISTORY_LENGTH:]

        builder = OrderBuilder(product, POSITION_LIMITS[product], state.position.get(product, 0))
        soft_limit = int(POSITION_LIMITS[product] * EMERALDS["SOFT_LIMIT_RATIO"])
        fair = (
            EMERALDS["ANCHOR_WEIGHT"] * EMERALDS["ANCHOR"]
            + EMERALDS["MID_WEIGHT"] * float(book["mid"])
        )
        fair -= builder.projected_position() * EMERALDS["INVENTORY_SKEW"]

        imbalance = float(book["l1_imbalance"])
        buy_trigger_bonus = EMERALDS["TAKE_IMBALANCE_BONUS"] if imbalance > 0.05 else 0.0
        sell_trigger_bonus = EMERALDS["TAKE_IMBALANCE_BONUS"] if imbalance < -0.05 else 0.0

        for price, volume in book["sell_levels"][:3]:
            distance = fair - price
            if distance < EMERALDS["TAKE_TIER_1_DISTANCE"] - buy_trigger_bonus:
                break
            if distance >= EMERALDS["TAKE_TIER_3_DISTANCE"]:
                size = EMERALDS["TAKE_TIER_3_SIZE"]
            elif distance >= EMERALDS["TAKE_TIER_2_DISTANCE"]:
                size = EMERALDS["TAKE_TIER_2_SIZE"]
            else:
                size = EMERALDS["TAKE_TIER_1_SIZE"]
            if builder.projected_position() <= -soft_limit:
                size += 4
            elif builder.projected_position() >= soft_limit:
                size = max(0, size - 3)
            builder.add_buy(price, min(volume, size))

        for price, volume in book["buy_levels"][:3]:
            distance = price - fair
            if distance < EMERALDS["TAKE_TIER_1_DISTANCE"] - sell_trigger_bonus:
                break
            if distance >= EMERALDS["TAKE_TIER_3_DISTANCE"]:
                size = EMERALDS["TAKE_TIER_3_SIZE"]
            elif distance >= EMERALDS["TAKE_TIER_2_DISTANCE"]:
                size = EMERALDS["TAKE_TIER_2_SIZE"]
            else:
                size = EMERALDS["TAKE_TIER_1_SIZE"]
            if builder.projected_position() >= soft_limit:
                size += 4
            elif builder.projected_position() <= -soft_limit:
                size = max(0, size - 3)
            builder.add_sell(price, min(volume, size))

        projected = builder.projected_position()
        best_bid = int(book["best_bid"])
        best_ask = int(book["best_ask"])
        if projected > 0 and best_bid >= math.ceil(fair + EMERALDS["CLEAR_WIDTH"]):
            builder.add_sell(best_bid, min(projected, int(book["best_bid_volume"]), EMERALDS["BASE_ORDER_SIZE"]))
        projected = builder.projected_position()
        if projected < 0 and best_ask <= math.floor(fair - EMERALDS["CLEAR_WIDTH"]):
            builder.add_buy(best_ask, min(abs(projected), int(book["best_ask_volume"]), EMERALDS["BASE_ORDER_SIZE"]))

        buy_quote = round(fair - EMERALDS["DEFAULT_EDGE"])
        sell_quote = round(fair + EMERALDS["DEFAULT_EDGE"])

        asks_above_fair = [price for price, _ in book["sell_levels"] if price > fair + EMERALDS["DISREGARD_EDGE"]]
        bids_below_fair = [price for price, _ in book["buy_levels"] if price < fair - EMERALDS["DISREGARD_EDGE"]]
        best_ask_above_fair = min(asks_above_fair) if asks_above_fair else None
        best_bid_below_fair = max(bids_below_fair) if bids_below_fair else None

        if best_ask_above_fair is not None:
            if abs(best_ask_above_fair - fair) <= EMERALDS["JOIN_EDGE"]:
                sell_quote = best_ask_above_fair
            else:
                sell_quote = best_ask_above_fair - 1
        if best_bid_below_fair is not None:
            if abs(fair - best_bid_below_fair) <= EMERALDS["JOIN_EDGE"]:
                buy_quote = best_bid_below_fair
            else:
                buy_quote = best_bid_below_fair + 1

        projected = builder.projected_position()
        if projected >= soft_limit:
            buy_quote -= 1
            sell_quote -= 1
        elif projected <= -soft_limit:
            buy_quote += 1
            sell_quote += 1

        buy_quote, sell_quote = self.clamp_inside_spread(book, buy_quote, sell_quote)

        if buy_quote is not None and builder.buy_capacity > 0 and projected < soft_limit + EMERALDS["BASE_ORDER_SIZE"]:
            size = EMERALDS["BASE_ORDER_SIZE"] + (1 if int(book["spread"]) >= 16 else 0)
            if projected <= -soft_limit:
                size += 4
            elif projected >= soft_limit:
                size = max(1, size - 6)
            builder.add_buy(buy_quote, size)

        projected = builder.projected_position()
        if sell_quote is not None and builder.sell_capacity > 0 and projected > -(soft_limit + EMERALDS["BASE_ORDER_SIZE"]):
            size = EMERALDS["BASE_ORDER_SIZE"] + (1 if int(book["spread"]) >= 16 else 0)
            if projected >= soft_limit:
                size += 4
            elif projected <= -soft_limit:
                size = max(1, size - 6)
            builder.add_sell(sell_quote, size)

        return builder.orders

    def trade_tomatoes(
        self,
        state: TradingState,
        product: str,
        history: Dict[str, List[float]],
        memory: Dict[str, object],
    ) -> Tuple[List[Order], Dict[str, object]]:
        product_history = history.get(product, [])
        book = self.get_book(state.order_depths[product], product_history)
        if book is None:
            return [], memory

        previous_book = self.previous_book_snapshot(memory)
        current_book = self.current_book_snapshot(book)
        flow_features = self.level_flow_features(previous_book, current_book)
        ml_imbalance = self.multi_level_imbalance(book)
        volatility = self.realized_volatility(product_history, int(book["spread"]))
        stretch = clip((float(book["mid"]) - float(book["ma20"])) / max(1.0, volatility), -3.0, 3.0)

        taker_beta = self.load_vector(memory, "taker_beta", TAKER_FEATURE_DIM)
        taker_p_matrix = self.load_matrix(memory, "taker_p_matrix", TAKER_FEATURE_DIM, TOMATOES["TAKER_RLS_DELTA"])
        maker_beta = self.load_vector(memory, "maker_beta", MAKER_FEATURE_DIM)
        maker_p_matrix = self.load_matrix(memory, "maker_p_matrix", MAKER_FEATURE_DIM, TOMATOES["MAKER_RLS_DELTA"])
        taker_scales = self.load_feature_scales(memory, "taker_scales", TAKER_FEATURE_DIM)
        maker_scales = self.load_feature_scales(memory, "maker_scales", MAKER_FEATURE_DIM)
        previous_regime = self.load_regime_memory(memory)
        passive_stats = self.load_passive_stats(memory)
        passive_stats = self.decay_passive_stats(passive_stats)
        passive_bucket_stats = self.load_passive_bucket_stats(memory)
        passive_bucket_stats = self.decay_passive_bucket_stats(passive_bucket_stats)
        taker_bucket_stats = self.load_taker_bucket_stats(memory)
        taker_bucket_stats = self.decay_taker_bucket_stats(taker_bucket_stats)
        resting_quotes = self.load_resting_quotes(memory)

        buy_bias = float(memory.get("adverse_buy_bias", 0.0)) * TOMATOES["POST_FILL_DECAY"]
        sell_bias = float(memory.get("adverse_sell_bias", 0.0)) * TOMATOES["POST_FILL_DECAY"]
        last_fill_ts = int(memory.get("last_fill_ts", -1))

        last_fill_ts, resting_quotes, new_pending = self.attribute_passive_fills(
            state,
            product,
            resting_quotes,
            last_fill_ts,
            passive_stats,
            passive_bucket_stats,
            float(book["mid"]),
        )

        pending_fills: List[Dict[str, object]] = []
        raw_pending = memory.get("pending_passive_fills", [])
        if isinstance(raw_pending, list):
            for item in raw_pending:
                if isinstance(item, dict):
                    pending_fills.append(item)
        pending_fills.extend(new_pending)

        pending_taker_trades: List[Dict[str, object]] = []
        raw_pending_taker = memory.get("pending_taker_trades", [])
        if isinstance(raw_pending_taker, list):
            for item in raw_pending_taker:
                if isinstance(item, dict):
                    pending_taker_trades.append(item)

        preliminary_toxic = softmax(
            {
                "trend_up": 0.0,
                "trend_down": 0.0,
                "range": 0.0,
                "toxic": (
                    TOMATOES["REGIME_TOXIC_COEF"] * (int(book["spread"]) - TOMATOES["TOXIC_SPREAD"]) / 4.0
                    + 0.90 * (volatility - TOMATOES["TOXIC_VOL"])
                ),
            }
        )["toxic"]

        pending_fills, maker_beta, maker_p_matrix, passive_stats, passive_bucket_stats, buy_bias, sell_bias = self.process_matured_passive_fills(
            state,
            pending_fills,
            maker_beta,
            maker_p_matrix,
            passive_stats,
            passive_bucket_stats,
            float(book["mid"]),
            volatility,
            buy_bias,
            sell_bias,
            float(book["spread"]),
            preliminary_toxic,
        )
        pending_taker_trades, taker_bucket_stats = self.process_matured_taker_trades(
            state,
            pending_taker_trades,
            taker_bucket_stats,
            float(book["mid"]),
        )

        taker_raw = self.taker_raw_features(book, ml_imbalance, flow_features, volatility)
        taker_features, taker_scales = self.update_scales(taker_raw, taker_scales)
        last_taker_features = memory.get("last_taker_features")
        last_mid = memory.get("last_mid")
        if (
            isinstance(last_taker_features, list)
            and len(last_taker_features) == TAKER_FEATURE_DIM
            and isinstance(last_mid, (int, float))
            and float(book["spread"]) < TOMATOES["RLS_SKIP_SPREAD"]
            and preliminary_toxic < TOMATOES["RLS_SKIP_TOXIC"]
        ):
            target = clip(float(book["mid"]) - float(last_mid), -TOMATOES["TAKER_TARGET_CLIP"], TOMATOES["TAKER_TARGET_CLIP"])
            taker_beta, taker_p_matrix = self.update_model(
                taker_beta,
                taker_p_matrix,
                [float(value) for value in last_taker_features],
                target,
                TOMATOES["TAKER_RLS_LAMBDA"],
                TOMATOES["TAKER_BETA_CLIP"],
            )

        taker_signal = clip(self.predict(taker_beta, taker_features), -4.0, 4.0)
        reversion_signal = -stretch
        taker_alpha = taker_signal + TOMATOES["REVERSION_ALPHA_WEIGHT"] * reversion_signal

        regime = self.regime_weights(
            taker_alpha,
            volatility,
            int(book["spread"]),
            ml_imbalance,
            flow_features,
            stretch,
            previous_regime,
        )

        buy_maker_raw = self.maker_raw_features("BUY", book, ml_imbalance, flow_features, volatility, stretch)
        buy_maker_features, maker_scales = self.update_scales(buy_maker_raw, maker_scales)
        sell_maker_raw = self.maker_raw_features("SELL", book, ml_imbalance, flow_features, volatility, stretch)
        sell_maker_features = [
            1.0 if index == 0 else clip(sell_maker_raw[index] / maker_scales[index], -TOMATOES["FEATURE_CLIP"], TOMATOES["FEATURE_CLIP"])
            for index in range(MAKER_FEATURE_DIM)
        ]
        buy_score, sell_score = self.maker_scores(maker_beta, buy_maker_features, sell_maker_features)

        position = state.position.get(product, 0)
        soft_limit = self.dynamic_soft_limit(regime, POSITION_LIMITS[product])
        buy_target_markout = self.taker_markout_adjustment("BUY", taker_alpha, stretch, regime, volatility, taker_bucket_stats)
        sell_target_markout = self.taker_markout_adjustment("SELL", taker_alpha, stretch, regime, volatility, taker_bucket_stats)
        target_position = self.target_position(
            regime,
            taker_alpha,
            stretch,
            soft_limit,
            volatility,
            position,
            buy_target_markout if taker_alpha >= 0 else sell_target_markout,
        )
        tau = self.time_fraction_remaining(state)

        fair_value = float(book["mid"]) + TOMATOES["CENTER_ALPHA_WEIGHT"] * taker_alpha
        reservation = self.reservation_price(fair_value, position, target_position, volatility, tau, regime)

        builder = OrderBuilder(product, POSITION_LIMITS[product], position)
        current_ts = float(getattr(state, "timestamp", 0))
        buy_taker_bucket = self.taker_bucket_key("BUY", taker_alpha, stretch, regime, volatility)
        sell_taker_bucket = self.taker_bucket_key("SELL", taker_alpha, stretch, regime, volatility)

        pre_base_half_spread = self.base_quote_half_spread(
            book,
            position,
            target_position,
            soft_limit,
            volatility,
            regime,
            buy_bias,
            sell_bias,
        )
        pre_buy_offset, pre_sell_offset = self.side_quote_offsets(
            pre_base_half_spread,
            position,
            target_position,
            soft_limit,
            buy_score,
            sell_score,
            buy_bias,
            sell_bias,
        )
        pre_buy_quote, pre_sell_quote = self.clamp_inside_spread(
            book,
            math.floor(reservation - pre_buy_offset),
            math.ceil(reservation + pre_sell_offset),
        )
        pre_buy_ev = None
        pre_sell_ev = None
        if pre_buy_quote is not None:
            pre_buy_ev = self.passive_expected_value(
                "BUY",
                pre_buy_quote,
                reservation,
                buy_score,
                book,
                position - target_position,
                soft_limit,
                regime,
                buy_bias,
                volatility,
                passive_stats,
                passive_bucket_stats,
            )
        if pre_sell_quote is not None:
            pre_sell_ev = self.passive_expected_value(
                "SELL",
                pre_sell_quote,
                reservation,
                sell_score,
                book,
                position - target_position,
                soft_limit,
                regime,
                sell_bias,
                volatility,
                passive_stats,
                passive_bucket_stats,
            )

        buy_edge = self.take_edge(
            "BUY",
            builder.projected_position(),
            target_position,
            taker_alpha,
            stretch,
            regime,
            buy_bias,
            volatility,
            taker_bucket_stats,
        )
        sell_edge = self.take_edge(
            "SELL",
            builder.projected_position(),
            target_position,
            taker_alpha,
            stretch,
            regime,
            sell_bias,
            volatility,
            taker_bucket_stats,
        )
        taker_fair = float(book["mid"]) + taker_alpha
        buy_take_ev = self.aggressive_expected_value(
            "BUY",
            book,
            position,
            target_position,
            soft_limit,
            taker_fair,
            buy_edge,
        )
        sell_take_ev = self.aggressive_expected_value(
            "SELL",
            book,
            position,
            target_position,
            soft_limit,
            taker_fair,
            sell_edge,
        )

        chosen_take_sides: List[Tuple[float, str]] = []
        flow_score = flow_features[3] + 0.35 * flow_features[4]
        buy_take_gate = max(0.0, pre_buy_ev if pre_buy_ev is not None else -999.0) + TOMATOES["TAKE_EV_MARGIN"]
        sell_take_gate = max(0.0, pre_sell_ev if pre_sell_ev is not None else -999.0) + TOMATOES["TAKE_EV_MARGIN"]
        if buy_take_ev > buy_take_gate:
            chosen_take_sides.append((buy_take_ev, "BUY"))
        if sell_take_ev > sell_take_gate:
            chosen_take_sides.append((sell_take_ev, "SELL"))
        chosen_take_sides.sort(reverse=True)

        for _ev, side in chosen_take_sides:
            projected = builder.projected_position()
            edge = self.take_edge(
                side,
                projected,
                target_position,
                taker_alpha,
                stretch,
                regime,
                buy_bias if side == "BUY" else sell_bias,
                volatility,
                taker_bucket_stats,
            )
            self.sweep_book(
                side,
                book,
                builder,
                taker_fair,
                edge,
                target_position,
                soft_limit,
                current_ts,
                float(book["mid"]),
                buy_taker_bucket if side == "BUY" else sell_taker_bucket,
                pending_taker_trades,
                regime,
                taker_alpha,
                flow_score,
                ml_imbalance,
            )

        projected = builder.projected_position()
        reservation = self.reservation_price(fair_value, projected, target_position, volatility, tau, regime)
        base_half_spread = self.base_quote_half_spread(
            book,
            projected,
            target_position,
            soft_limit,
            volatility,
            regime,
            buy_bias,
            sell_bias,
        )
        buy_offset, sell_offset = self.side_quote_offsets(
            base_half_spread,
            projected,
            target_position,
            soft_limit,
            buy_score,
            sell_score,
            buy_bias,
            sell_bias,
        )
        buy_quote, sell_quote = self.clamp_inside_spread(
            book,
            math.floor(reservation - buy_offset),
            math.ceil(reservation + sell_offset),
        )

        buy_ev = None
        sell_ev = None
        if buy_quote is not None:
            buy_ev = self.passive_expected_value(
                "BUY",
                buy_quote,
                reservation,
                buy_score,
                book,
                projected - target_position,
                soft_limit,
                regime,
                buy_bias,
                volatility,
                passive_stats,
                passive_bucket_stats,
            )
        if sell_quote is not None:
            sell_ev = self.passive_expected_value(
                "SELL",
                sell_quote,
                reservation,
                sell_score,
                book,
                projected - target_position,
                soft_limit,
                regime,
                sell_bias,
                volatility,
                passive_stats,
                passive_bucket_stats,
            )

        if (
            buy_quote is not None
            and buy_ev is not None
            and buy_ev >= TOMATOES["PASSIVE_MIN_EV"]
            and self.should_allow_passive_side(
                "BUY",
                projected,
                target_position,
                soft_limit,
                regime,
                buy_ev,
                sell_ev if sell_ev is not None else -999.0,
                buy_score,
                sell_score,
                buy_bias,
                sell_bias,
            )
            and builder.buy_capacity > 0
        ):
            size = min(
                self.passive_size("BUY", projected, target_position, soft_limit, regime),
                builder.buy_capacity,
            )
            if projected < target_position:
                size = min(size, max(1, target_position - projected))
            builder.add_buy(buy_quote, size)
            passive_stats["BUY"]["posted_qty"] += size
            buy_bucket = self.passive_bucket_key("BUY", buy_quote, book, regime, projected - target_position, soft_limit)
            passive_bucket_stats.setdefault(
                buy_bucket,
                {"posted": 0.0, "filled": 0.0, "markout": 0.0, "edge": 0.0},
            )["posted"] += size
            resting_quotes.append(
                {
                    "side": "BUY",
                    "price": int(buy_quote),
                    "timestamp": current_ts,
                    "mid": float(book["mid"]),
                    "fill_mid": float(book["mid"]),
                    "center": reservation,
                    "bucket": buy_bucket,
                    "qty": int(size),
                    "filled_qty": 0,
                    "features": buy_maker_features,
                }
            )

        projected = builder.projected_position()
        if sell_quote is not None:
            sell_ev = self.passive_expected_value(
                "SELL",
                sell_quote,
                reservation,
                sell_score,
                book,
                projected - target_position,
                soft_limit,
                regime,
                sell_bias,
                volatility,
                passive_stats,
                passive_bucket_stats,
            )
        if (
            sell_quote is not None
            and sell_ev is not None
            and sell_ev >= TOMATOES["PASSIVE_MIN_EV"]
            and self.should_allow_passive_side(
                "SELL",
                projected,
                target_position,
                soft_limit,
                regime,
                buy_ev if buy_ev is not None else -999.0,
                sell_ev,
                buy_score,
                sell_score,
                buy_bias,
                sell_bias,
            )
            and builder.sell_capacity > 0
        ):
            size = min(
                self.passive_size("SELL", projected, target_position, soft_limit, regime),
                builder.sell_capacity,
            )
            if projected > target_position:
                size = min(size, max(1, projected - target_position))
            builder.add_sell(sell_quote, size)
            passive_stats["SELL"]["posted_qty"] += size
            sell_bucket = self.passive_bucket_key("SELL", sell_quote, book, regime, projected - target_position, soft_limit)
            passive_bucket_stats.setdefault(
                sell_bucket,
                {"posted": 0.0, "filled": 0.0, "markout": 0.0, "edge": 0.0},
            )["posted"] += size
            resting_quotes.append(
                {
                    "side": "SELL",
                    "price": int(sell_quote),
                    "timestamp": current_ts,
                    "mid": float(book["mid"]),
                    "fill_mid": float(book["mid"]),
                    "center": reservation,
                    "bucket": sell_bucket,
                    "qty": int(size),
                    "filled_qty": 0,
                    "features": sell_maker_features,
                }
            )

        resting_quotes = [
            quote
            for quote in resting_quotes[-TOMATOES["MAX_RESTING_QUOTES"] :]
            if current_ts - float(quote["timestamp"]) <= TOMATOES["QUOTE_MEMORY_TICKS"]
        ]

        product_history.append(float(book["mid"]))
        history[product] = product_history[-HISTORY_LENGTH:]

        next_memory = {
            "book": current_book,
            "taker_beta": taker_beta,
            "taker_p_matrix": taker_p_matrix,
            "maker_beta": maker_beta,
            "maker_p_matrix": maker_p_matrix,
            "taker_scales": taker_scales,
            "maker_scales": maker_scales,
            "last_taker_features": taker_features,
            "last_mid": float(book["mid"]),
            "regime": regime,
            "adverse_buy_bias": buy_bias,
            "adverse_sell_bias": sell_bias,
            "last_fill_ts": last_fill_ts,
            "pending_passive_fills": pending_fills[-16:],
            "pending_taker_trades": pending_taker_trades[-20:],
            "resting_quotes": resting_quotes[-TOMATOES["MAX_RESTING_QUOTES"] :],
            "passive_stats": passive_stats,
            "passive_bucket_stats": passive_bucket_stats,
            "taker_bucket_stats": taker_bucket_stats,
        }
        return builder.orders, next_memory

    def passive_size(
        self,
        side: str,
        position: int,
        target_position: int,
        soft_limit: int,
        regime: Dict[str, float],
    ) -> int:
        size = TOMATOES["PASSIVE_SIZE"]
        if regime["toxic"] > 0.45:
            size = max(1, size - 2)
        if side == "BUY":
            if position < target_position:
                size += 1
            if position >= soft_limit:
                size = max(1, size - 3)
        else:
            if position > target_position:
                size += 1
            if position <= -soft_limit:
                size = max(1, size - 3)
        return max(1, min(12, size))

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        mid_history, memory = self.load_trader_data(state.traderData)
        next_memory: Dict[str, Dict[str, object]] = dict(memory)

        for product in state.order_depths:
            if product == "EMERALDS":
                result[product] = self.trade_emeralds(state, product, mid_history)
            elif product == "TOMATOES":
                orders, product_memory = self.trade_tomatoes(
                    state,
                    product,
                    mid_history,
                    memory.get(product, {}),
                )
                result[product] = orders
                next_memory[product] = product_memory
            else:
                result[product] = []

        trader_data = self.build_trader_data(mid_history, next_memory)
        conversions = 0
        return result, conversions, trader_data
