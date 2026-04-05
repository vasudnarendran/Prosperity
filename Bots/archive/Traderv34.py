from datamodel import OrderDepth, Order, Trade, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


POSITION_LIMITS: Dict[str, int] = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}

HISTORY_LENGTH = 24

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
    "INVENTORY_SKEW": 0.032,
    "BASE_TAKE_EDGE": 1.10,
    "BASE_QUOTE_EDGE": 2.25,
    "MAX_QUOTE_EDGE": 5.25,
    "PASSIVE_SIZE": 8,
    "MAX_TAKE_SIZE": 10,
    "TOXIC_SPREAD": 15.0,
    "TOXIC_VOL": 3.1,
    "TIME_HORIZON_TICKS": 10000.0,
    "SOFT_LIMIT_BASE": 0.44,
    "SOFT_LIMIT_TREND_BONUS": 0.18,
    "SOFT_LIMIT_TOXIC_PENALTY": 0.10,
    "RLS_LAMBDA": 0.988,
    "RLS_DELTA": 6.0,
    "RLS_SKIP_SPREAD": 16.0,
    "RLS_SKIP_TOXIC": 0.60,
    "RLS_TARGET_CLIP": 3.5,
    "RLS_FEATURE_CLIP": 3.0,
    "RLS_BETA_CLIP": 1.50,
    "REVERSION_WEIGHT": 0.55,
    "REVERSION_BRAKE": 0.45,
    "MAKER_LEARNED_WEIGHT": 0.45,
    "TAKER_LEARNED_WEIGHT": 1.00,
    "MAKER_REVERSION_WEIGHT": 0.70,
    "TAKER_REVERSION_WEIGHT": 0.30,
    "AS_GAMMA_RANGE": 0.11,
    "AS_GAMMA_TREND": 0.08,
    "AS_GAMMA_TOXIC": 0.18,
    "AS_RESERVATION_SCALE": 0.17,
    "SPREAD_VOL_COEF": 0.72,
    "SPREAD_INV_COEF": 0.36,
    "SPREAD_TOXIC_COEF": 0.75,
    "SPREAD_ALPHA_REBATE": 0.28,
    "PASSIVE_MIN_EV": 0.03,
    "QUEUE_VALUE_COEF": 0.40,
    "PASSIVE_ADVERSE_COEF": 0.60,
    "PASSIVE_EDGE_MOVE_COST": 0.35,
    "POST_FILL_DECAY": 0.70,
    "POST_FILL_MAX_BIAS": 2.0,
    "POST_FILL_QUOTE_PENALTY": 0.30,
    "POST_FILL_TAKE_PENALTY": 0.18,
    "MARKOUT_DELAY_TICKS": 400,
    "MARKOUT_SCALE": 0.25,
    "REGIME_TREND_COEF": 1.40,
    "REGIME_FLOW_COEF": 0.85,
    "REGIME_TOXIC_COEF": 1.10,
}

FEATURE_DIM = 7


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
        return json.dumps(
            {"mid_history": mid_history, "memory": memory},
            separators=(",", ":"),
        )

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

    def order_flow_imbalance(
        self,
        previous_book: Dict[str, List[List[int]]],
        current_book: Dict[str, List[List[int]]],
    ) -> float:
        score = 0.0
        normalizer = 0.0
        for side, sign in (("buy", 1.0), ("sell", -1.0)):
            previous_map = {int(price): int(volume) for price, volume in previous_book.get(side, [])}
            current_map = {int(price): int(volume) for price, volume in current_book.get(side, [])}
            for price in set(previous_map) | set(current_map):
                prev_volume = previous_map.get(price, 0)
                curr_volume = current_map.get(price, 0)
                score += sign * (curr_volume - prev_volume)
                normalizer += max(prev_volume, curr_volume)
        return score / max(25.0, normalizer)

    def load_beta(self, memory: Dict[str, object]) -> List[float]:
        raw = memory.get("beta")
        if not isinstance(raw, list) or len(raw) != FEATURE_DIM:
            return [0.0] * FEATURE_DIM
        return [float(value) if isinstance(value, (int, float)) else 0.0 for value in raw]

    def load_p_matrix(self, memory: Dict[str, object]) -> List[List[float]]:
        fallback = [
            [TOMATOES["RLS_DELTA"] if row == col else 0.0 for col in range(FEATURE_DIM)]
            for row in range(FEATURE_DIM)
        ]
        raw = memory.get("p_matrix")
        if not isinstance(raw, list) or len(raw) != FEATURE_DIM:
            return fallback

        matrix: List[List[float]] = []
        for row, default_row in zip(raw, fallback):
            if not isinstance(row, list) or len(row) != FEATURE_DIM:
                matrix.append(default_row[:])
                continue
            matrix.append(
                [
                    float(value) if isinstance(value, (int, float)) else default
                    for value, default in zip(row, default_row)
                ]
            )
        return matrix

    def update_rls(
        self,
        beta: List[float],
        p_matrix: List[List[float]],
        last_features: object,
        last_mid: object,
        current_mid: float,
        spread: float,
        toxic_score: float,
    ) -> Tuple[List[float], List[List[float]]]:
        if not isinstance(last_features, list) or len(last_features) != FEATURE_DIM:
            return beta, p_matrix
        if not isinstance(last_mid, (int, float)):
            return beta, p_matrix
        if spread >= TOMATOES["RLS_SKIP_SPREAD"] or toxic_score >= TOMATOES["RLS_SKIP_TOXIC"]:
            return beta, p_matrix

        x = [clip(float(value), -TOMATOES["RLS_FEATURE_CLIP"], TOMATOES["RLS_FEATURE_CLIP"]) for value in last_features]
        y = clip(current_mid - float(last_mid), -TOMATOES["RLS_TARGET_CLIP"], TOMATOES["RLS_TARGET_CLIP"])

        p_times_x = [
            sum(p_matrix[row][col] * x[col] for col in range(FEATURE_DIM))
            for row in range(FEATURE_DIM)
        ]
        denom = TOMATOES["RLS_LAMBDA"] + sum(x[index] * p_times_x[index] for index in range(FEATURE_DIM))
        if abs(denom) <= 1e-9:
            return beta, p_matrix

        gain = [value / denom for value in p_times_x]
        prediction = sum(beta[index] * x[index] for index in range(FEATURE_DIM))
        error = y - prediction

        next_beta = [
            clip(beta[index] + gain[index] * error, -TOMATOES["RLS_BETA_CLIP"], TOMATOES["RLS_BETA_CLIP"])
            for index in range(FEATURE_DIM)
        ]

        x_t_p = [
            sum(x[row] * p_matrix[row][col] for row in range(FEATURE_DIM))
            for col in range(FEATURE_DIM)
        ]
        next_matrix: List[List[float]] = []
        for row in range(FEATURE_DIM):
            next_row: List[float] = []
            for col in range(FEATURE_DIM):
                updated = (p_matrix[row][col] - (gain[row] * x_t_p[col])) / TOMATOES["RLS_LAMBDA"]
                next_row.append(updated)
            next_matrix.append(next_row)
        return next_beta, next_matrix

    def update_markout_bias(
        self,
        state: TradingState,
        product: str,
        memory: Dict[str, object],
        current_mid: float,
    ) -> Tuple[float, float, int, List[Dict[str, float]]]:
        buy_bias = float(memory.get("adverse_buy_bias", 0.0)) * TOMATOES["POST_FILL_DECAY"]
        sell_bias = float(memory.get("adverse_sell_bias", 0.0)) * TOMATOES["POST_FILL_DECAY"]
        last_fill_ts = int(memory.get("last_fill_ts", -1))

        pending_raw = memory.get("pending_passive_fills", [])
        pending_fills: List[Dict[str, float]] = []
        if isinstance(pending_raw, list):
            for item in pending_raw:
                if isinstance(item, dict):
                    try:
                        pending_fills.append(
                            {
                                "side": str(item.get("side", "")),
                                "timestamp": float(item.get("timestamp", 0)),
                                "mid": float(item.get("mid", current_mid)),
                                "qty": float(item.get("qty", 1)),
                            }
                        )
                    except (TypeError, ValueError):
                        continue

        still_pending: List[Dict[str, float]] = []
        for fill in pending_fills:
            age = float(getattr(state, "timestamp", 0)) - fill["timestamp"]
            if age < TOMATOES["MARKOUT_DELAY_TICKS"]:
                still_pending.append(fill)
                continue

            markout = current_mid - fill["mid"]
            step = min(
                TOMATOES["POST_FILL_MAX_BIAS"],
                0.05 * fill["qty"] + TOMATOES["MARKOUT_SCALE"] * min(3.0, abs(markout)),
            )
            if fill["side"] == "BUY":
                if markout < 0:
                    buy_bias = min(TOMATOES["POST_FILL_MAX_BIAS"], buy_bias + step)
                else:
                    buy_bias = max(0.0, buy_bias - 0.50 * step)
            elif fill["side"] == "SELL":
                if markout > 0:
                    sell_bias = min(TOMATOES["POST_FILL_MAX_BIAS"], sell_bias + step)
                else:
                    sell_bias = max(0.0, sell_bias - 0.50 * step)

        last_passive_buy = memory.get("last_passive_buy")
        last_passive_sell = memory.get("last_passive_sell")

        for trade in state.own_trades.get(product, []):
            if not isinstance(trade, Trade):
                continue
            trade_ts = int(getattr(trade, "timestamp", -1))
            if trade_ts <= last_fill_ts:
                continue
            last_fill_ts = max(last_fill_ts, trade_ts)

            qty = float(max(1, abs(int(getattr(trade, "quantity", 0)))))
            if getattr(trade, "buyer", None) == "SUBMISSION" and last_passive_buy is not None and int(trade.price) == int(last_passive_buy):
                still_pending.append(
                    {
                        "side": "BUY",
                        "timestamp": float(trade_ts),
                        "mid": current_mid,
                        "qty": qty,
                    }
                )
            if getattr(trade, "seller", None) == "SUBMISSION" and last_passive_sell is not None and int(trade.price) == int(last_passive_sell):
                still_pending.append(
                    {
                        "side": "SELL",
                        "timestamp": float(trade_ts),
                        "mid": current_mid,
                        "qty": qty,
                    }
                )

        return buy_bias, sell_bias, last_fill_ts, still_pending

    def feature_vector(
        self,
        book: Dict[str, object],
        history: List[float],
        ml_imbalance: float,
        ofi: float,
        volatility: float,
    ) -> List[float]:
        spread_scale = max(1.0, float(book["spread"]))
        vol_scale = max(1.0, volatility)
        return [
            1.0,
            clip((float(book["micro"]) - float(book["mid"])) / spread_scale, -2.0, 2.0),
            clip(float(book["l1_imbalance"]), -1.0, 1.0),
            clip(ml_imbalance, -1.5, 1.5),
            clip(ofi, -2.0, 2.0),
            clip(float(book["short_return"]) / vol_scale, -3.0, 3.0),
            clip(float(book["spread"]) / 16.0, 0.5, 2.0),
        ]

    def predicted_delta(self, beta: List[float], features: List[float]) -> float:
        return sum(weight * value for weight, value in zip(beta, features))

    def regime_weights(
        self,
        alpha_signal: float,
        volatility: float,
        spread: int,
        ml_imbalance: float,
        ofi: float,
        stretch: float,
    ) -> Dict[str, float]:
        trend_signal = alpha_signal / max(1.0, volatility)
        logits = {
            "trend_up": (
                TOMATOES["REGIME_TREND_COEF"] * trend_signal
                + TOMATOES["REGIME_FLOW_COEF"] * ofi
                + 0.35 * ml_imbalance
            ),
            "trend_down": (
                -TOMATOES["REGIME_TREND_COEF"] * trend_signal
                - TOMATOES["REGIME_FLOW_COEF"] * ofi
                - 0.35 * ml_imbalance
            ),
            "range": 0.40 - 0.90 * abs(trend_signal) - 0.35 * abs(ofi) - 0.20 * abs(stretch),
            "toxic": (
                TOMATOES["REGIME_TOXIC_COEF"] * (spread - TOMATOES["TOXIC_SPREAD"]) / 4.0
                + 0.90 * (volatility - TOMATOES["TOXIC_VOL"])
                + 0.65 * abs(ofi)
            ),
        }
        return softmax(logits)

    def dynamic_soft_limit(self, regime: Dict[str, float], position_limit: int) -> int:
        ratio = (
            TOMATOES["SOFT_LIMIT_BASE"]
            + TOMATOES["SOFT_LIMIT_TREND_BONUS"] * max(regime["trend_up"], regime["trend_down"])
            - TOMATOES["SOFT_LIMIT_TOXIC_PENALTY"] * regime["toxic"]
        )
        return max(12, min(position_limit, int(position_limit * clip(ratio, 0.22, 0.72))))

    def target_position(
        self,
        regime: Dict[str, float],
        taker_alpha: float,
        stretch: float,
        soft_limit: int,
        volatility: float,
    ) -> int:
        trend_bias = regime["trend_up"] - regime["trend_down"]
        alpha_bias = math.tanh(taker_alpha / max(1.0, volatility))
        reversion_target = -0.30 * clip(stretch, -2.5, 2.5)
        target_score = 0.70 * trend_bias + 0.25 * alpha_bias + 0.20 * reversion_target
        if taker_alpha * stretch > 0:
            chase_penalty = min(0.60, TOMATOES["REVERSION_BRAKE"] * abs(stretch) / 3.0)
            target_score *= max(0.35, 1.0 - chase_penalty)
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

    def quote_half_spread(
        self,
        book: Dict[str, object],
        position_gap: float,
        soft_limit: int,
        volatility: float,
        maker_alpha: float,
        regime: Dict[str, float],
    ) -> float:
        half_spread = max(TOMATOES["BASE_QUOTE_EDGE"], float(book["spread"]) / 3.5)
        half_spread += TOMATOES["SPREAD_VOL_COEF"] * min(3.0, volatility)
        half_spread += TOMATOES["SPREAD_INV_COEF"] * min(1.0, abs(position_gap) / max(1, soft_limit))
        half_spread += TOMATOES["SPREAD_TOXIC_COEF"] * regime["toxic"]
        half_spread -= TOMATOES["SPREAD_ALPHA_REBATE"] * min(1.0, abs(maker_alpha) / max(1.0, volatility))
        return clip(half_spread, TOMATOES["BASE_QUOTE_EDGE"], TOMATOES["MAX_QUOTE_EDGE"])

    def passive_fill_probability(
        self,
        side: str,
        quote: int,
        book: Dict[str, object],
        regime: Dict[str, float],
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
        return clip(
            0.06
            + 0.42 * distance_factor
            + 0.12 * depth_factor
            + 0.08 * max(0.0, 1.0 - regime["toxic"]),
            0.05,
            0.88,
        )

    def passive_expected_value(
        self,
        side: str,
        quote: int,
        reservation: float,
        book: Dict[str, object],
        position_gap: float,
        soft_limit: int,
        regime: Dict[str, float],
        adverse_bias: float,
        volatility: float,
    ) -> float:
        raw_capture = (reservation - quote) if side == "BUY" else (quote - reservation)
        spread_capture = max(0.0, raw_capture)
        p_fill = self.passive_fill_probability(side, quote, book, regime)
        adverse_move = max(0.8, TOMATOES["PASSIVE_EDGE_MOVE_COST"] * max(1.0, volatility))
        adverse_risk = (
            0.15
            + TOMATOES["PASSIVE_ADVERSE_COEF"] * regime["toxic"]
            + TOMATOES["POST_FILL_QUOTE_PENALTY"] * adverse_bias
        )
        inventory_cost = 0.10 * abs(position_gap) / max(1, soft_limit)
        return (p_fill * spread_capture) - (adverse_risk * adverse_move) - inventory_cost

    def maker_quotes(
        self,
        book: Dict[str, object],
        reservation: float,
        maker_alpha: float,
        position: int,
        target_position: int,
        soft_limit: int,
        regime: Dict[str, float],
        buy_bias: float,
        sell_bias: float,
        volatility: float,
    ) -> Tuple[Optional[int], Optional[int]]:
        half_spread = self.quote_half_spread(
            book,
            position - target_position,
            soft_limit,
            volatility,
            maker_alpha,
            regime,
        )
        center = reservation + maker_alpha
        buy_quote = math.floor(center - half_spread)
        sell_quote = math.ceil(center + half_spread)

        if buy_bias > 0.0:
            buy_quote -= int(math.ceil(buy_bias))
        if sell_bias > 0.0:
            sell_quote += int(math.ceil(sell_bias))

        if position >= max(target_position, soft_limit):
            buy_quote -= 1
        if position <= min(target_position, -soft_limit):
            sell_quote += 1

        return self.clamp_inside_spread(book, buy_quote, sell_quote)

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
    ) -> float:
        edge = TOMATOES["BASE_TAKE_EDGE"]
        edge += 0.25 * regime["toxic"]
        edge += TOMATOES["POST_FILL_TAKE_PENALTY"] * adverse_bias
        edge += 0.10 * min(3.0, volatility)

        position_gap = position - target_position
        if side == "BUY" and position_gap < 0:
            edge -= 0.18
        if side == "SELL" and position_gap > 0:
            edge -= 0.18

        if side == "BUY" and taker_alpha > 0:
            edge -= min(0.40, 0.12 * taker_alpha)
        if side == "SELL" and taker_alpha < 0:
            edge -= min(0.40, 0.12 * abs(taker_alpha))

        if side == "BUY" and taker_alpha > 0 and stretch > 0:
            edge += TOMATOES["REVERSION_BRAKE"] * min(0.80, abs(stretch) / 3.0)
        if side == "SELL" and taker_alpha < 0 and stretch < 0:
            edge += TOMATOES["REVERSION_BRAKE"] * min(0.80, abs(stretch) / 3.0)

        return max(0.45, edge)

    def sweep_book(
        self,
        side: str,
        book: Dict[str, object],
        builder: OrderBuilder,
        fair_value: float,
        threshold: float,
        target_position: int,
        soft_limit: int,
    ) -> bool:
        traded = False
        levels = book["sell_levels"][:3] if side == "BUY" else book["buy_levels"][:3]
        for price, volume in levels:
            projected = builder.projected_position()
            edge = (fair_value - price) if side == "BUY" else (price - fair_value)
            if edge < threshold:
                break

            if side == "BUY":
                desired = max(0, target_position - projected)
                if projected < 0 and edge >= threshold + 0.8:
                    desired = max(desired, min(abs(projected), TOMATOES["MAX_TAKE_SIZE"]))
                quantity = min(volume, builder.buy_capacity, TOMATOES["MAX_TAKE_SIZE"], desired)
                if quantity <= 0:
                    continue
                builder.add_buy(price, quantity)
                traded = True
            else:
                desired = max(0, projected - target_position)
                if projected > 0 and edge >= threshold + 0.8:
                    desired = max(desired, min(projected, TOMATOES["MAX_TAKE_SIZE"]))
                quantity = min(volume, builder.sell_capacity, TOMATOES["MAX_TAKE_SIZE"], desired)
                if quantity <= 0:
                    continue
                builder.add_sell(price, quantity)
                traded = True
        return traded

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
            size = 0
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
            size = 0
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
            sell_quote = best_ask_above_fair if abs(best_ask_above_fair - fair) <= EMERALDS["JOIN_EDGE"] else best_ask_above_fair - 1
        if best_bid_below_fair is not None:
            buy_quote = best_bid_below_fair if abs(fair - best_bid_below_fair) <= EMERALDS["JOIN_EDGE"] else best_bid_below_fair + 1

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
        ml_imbalance = self.multi_level_imbalance(book)
        ofi = self.order_flow_imbalance(previous_book, current_book)
        volatility = self.realized_volatility(product_history, int(book["spread"]))
        stretch = clip((float(book["mid"]) - float(book["ma20"])) / max(1.0, volatility), -3.0, 3.0)

        preliminary_toxic = softmax(
            {
                "trend_up": 0.0,
                "trend_down": 0.0,
                "range": 0.0,
                "toxic": 1.10 * (int(book["spread"]) - TOMATOES["TOXIC_SPREAD"]) / 4.0 + 0.90 * (volatility - TOMATOES["TOXIC_VOL"]),
            }
        )["toxic"]

        beta = self.load_beta(memory)
        p_matrix = self.load_p_matrix(memory)
        beta, p_matrix = self.update_rls(
            beta,
            p_matrix,
            memory.get("last_features"),
            memory.get("last_mid"),
            float(book["mid"]),
            float(book["spread"]),
            preliminary_toxic,
        )

        buy_bias, sell_bias, last_fill_ts, pending_fills = self.update_markout_bias(
            state,
            product,
            memory,
            float(book["mid"]),
        )

        features = self.feature_vector(book, product_history, ml_imbalance, ofi, volatility)
        online_delta = self.predicted_delta(beta, features)
        reversion_alpha = -TOMATOES["REVERSION_WEIGHT"] * stretch

        maker_alpha = (
            TOMATOES["MAKER_LEARNED_WEIGHT"] * online_delta
            + TOMATOES["MAKER_REVERSION_WEIGHT"] * reversion_alpha
        )
        taker_alpha = (
            TOMATOES["TAKER_LEARNED_WEIGHT"] * online_delta
            + TOMATOES["TAKER_REVERSION_WEIGHT"] * reversion_alpha
        )

        regime = self.regime_weights(taker_alpha, volatility, int(book["spread"]), ml_imbalance, ofi, stretch)
        soft_limit = self.dynamic_soft_limit(regime, POSITION_LIMITS[product])
        position = state.position.get(product, 0)
        target_position = self.target_position(regime, taker_alpha, stretch, soft_limit, volatility)
        tau = self.time_fraction_remaining(state)

        maker_fair = float(book["mid"]) + maker_alpha - position * TOMATOES["INVENTORY_SKEW"]
        reservation = self.reservation_price(maker_fair, position, target_position, volatility, tau, regime)
        taker_fair = float(book["mid"]) + taker_alpha

        builder = OrderBuilder(product, POSITION_LIMITS[product], position)

        buy_edge = self.take_edge("BUY", builder.projected_position(), target_position, taker_alpha, stretch, regime, buy_bias, volatility)
        sell_edge = self.take_edge("SELL", builder.projected_position(), target_position, taker_alpha, stretch, regime, sell_bias, volatility)
        self.sweep_book("BUY", book, builder, taker_fair, buy_edge, target_position, soft_limit)
        self.sweep_book("SELL", book, builder, taker_fair, sell_edge, target_position, soft_limit)

        projected = builder.projected_position()
        buy_quote, sell_quote = self.maker_quotes(
            book,
            reservation,
            maker_alpha,
            projected,
            target_position,
            soft_limit,
            regime,
            buy_bias,
            sell_bias,
            volatility,
        )

        last_passive_buy = None
        last_passive_sell = None

        if buy_quote is not None and builder.buy_capacity > 0 and projected < soft_limit:
            buy_ev = self.passive_expected_value(
                "BUY",
                buy_quote,
                reservation,
                book,
                projected - target_position,
                soft_limit,
                regime,
                buy_bias,
                volatility,
            )
            if buy_ev >= TOMATOES["PASSIVE_MIN_EV"] and (regime["toxic"] < 0.65 or projected < 0):
                size = min(
                    self.passive_size("BUY", projected, target_position, soft_limit, regime),
                    builder.buy_capacity,
                )
                if projected < target_position:
                    size = min(size, max(1, target_position - projected))
                builder.add_buy(buy_quote, size)
                last_passive_buy = buy_quote

        projected = builder.projected_position()
        if sell_quote is not None and builder.sell_capacity > 0 and projected > -soft_limit:
            sell_ev = self.passive_expected_value(
                "SELL",
                sell_quote,
                reservation,
                book,
                projected - target_position,
                soft_limit,
                regime,
                sell_bias,
                volatility,
            )
            if sell_ev >= TOMATOES["PASSIVE_MIN_EV"] and (regime["toxic"] < 0.65 or projected > 0):
                size = min(
                    self.passive_size("SELL", projected, target_position, soft_limit, regime),
                    builder.sell_capacity,
                )
                if projected > target_position:
                    size = min(size, max(1, projected - target_position))
                builder.add_sell(sell_quote, size)
                last_passive_sell = sell_quote

        product_history.append(float(book["mid"]))
        history[product] = product_history[-HISTORY_LENGTH:]

        next_memory = {
            "beta": beta,
            "p_matrix": p_matrix,
            "last_features": features,
            "last_mid": float(book["mid"]),
            "book": current_book,
            "adverse_buy_bias": buy_bias,
            "adverse_sell_bias": sell_bias,
            "pending_passive_fills": pending_fills,
            "last_fill_ts": last_fill_ts,
            "last_passive_buy": last_passive_buy,
            "last_passive_sell": last_passive_sell,
        }
        return builder.orders, next_memory

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
