from datamodel import OrderDepth, Order, Trade, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


POSITION_LIMITS: Dict[str, int] = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}

EMERALDS = {
    "REFERENCE_PRICE": 10000.0,
    "REFERENCE_WEIGHT": 0.80,
    "MID_WEIGHT": 0.20,
    "MICRO_WEIGHT": 0.00,
    "INVENTORY_SKEW": 0.12,
    "TAKE_TIER_1_DISTANCE": 1.0,
    "TAKE_TIER_2_DISTANCE": 4.0,
    "TAKE_TIER_3_DISTANCE": 8.0,
    "TAKE_TIER_1_SIZE": 6,
    "TAKE_TIER_2_SIZE": 12,
    "TAKE_TIER_3_SIZE": 20,
    "CLEAR_WIDTH": 0.0,
    "BASE_ORDER_SIZE": 10,
    "DISREGARD_EDGE": 2.0,
    "JOIN_EDGE": 1.0,
    "DEFAULT_EDGE": 8.0,
    "SOFT_LIMIT_RATIO": 0.25,
}

TOMATOES = {
    "INVENTORY_SKEW": 0.03,
    "TAKE_EDGE": 1.0,
    "QUOTE_EDGE": 1.8,
    "MAX_QUOTE_EDGE": 5.5,
    "PASSIVE_SIZE": 8,
    "MAX_TAKE_SIZE": 10,
    "TOXIC_SPREAD": 15.0,
    "TOXIC_VOL": 3.0,
    "TIME_HORIZON_TICKS": 10000.0,
    "SOFT_LIMIT_BASE": 0.42,
    "SOFT_LIMIT_TREND_BONUS": 0.22,
    "SOFT_LIMIT_TOXIC_PENALTY": 0.10,
    "MAKER_ALPHA_SCALE": 0.55,
    "TAKER_ALPHA_SCALE": 1.00,
    "OFI_WEIGHT": 0.60,
    "ML_IMBALANCE_WEIGHT": 0.35,
    "RLS_LAMBDA": 0.985,
    "RLS_DELTA": 8.0,
    "AS_GAMMA_BASE": 0.10,
    "AS_GAMMA_TREND": 0.08,
    "AS_GAMMA_TOXIC": 0.18,
    "AS_RES_SCALE": 0.18,
    "SPREAD_VOL_COEF": 0.75,
    "SPREAD_INV_COEF": 0.35,
    "SPREAD_TOXIC_COEF": 0.70,
    "SPREAD_ALPHA_REBATE": 0.30,
    "PASSIVE_MIN_EV": 0.05,
    "QUEUE_VALUE_COEF": 0.45,
    "PASSIVE_ADVERSE_COEF": 0.75,
    "POST_FILL_DECAY": 0.65,
    "POST_FILL_MAX_BIAS": 2.0,
    "POST_FILL_QUOTE_PENALTY": 0.45,
    "POST_FILL_TAKE_PENALTY": 0.30,
    "MARKOUT_DELAY_TICKS": 400,
    "MARKOUT_SCALE": 0.30,
    "RLS_SKIP_SPREAD": 16.0,
    "RLS_SKIP_TOXIC": 0.55,
    "RLS_TARGET_CLIP": 3.0,
    "RLS_BETA_CLIP": 1.50,
    "RESIDUAL_ALPHA_WEIGHT": 0.20,
    "MOMENTUM_RESIDUAL_WEIGHT": 0.05,
    "REGIME_TREND_COEF": 1.35,
    "REGIME_FLOW_COEF": 0.75,
    "REGIME_TOXIC_COEF": 1.20,
}

HISTORY_LENGTH = 12
FEATURE_NAMES = [
    "bias",
    "micro_gap",
    "l1_imbalance",
    "ml_imbalance",
    "ofi",
    "momentum",
    "spread_norm",
]


def sigmoid(value: float) -> float:
    clipped = max(-12.0, min(12.0, value))
    return 1.0 / (1.0 + math.exp(-clipped))


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

        raw_history = parsed.get("mid_history", {})
        raw_memory = parsed.get("memory", {})

        history: Dict[str, List[float]] = {}
        if isinstance(raw_history, dict):
            for product, values in raw_history.items():
                if isinstance(values, list):
                    history[product] = [float(value) for value in values[-HISTORY_LENGTH:]]

        memory: Dict[str, Dict[str, object]] = {}
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
        payload = {
            "mid_history": mid_history,
            "memory": memory,
        }
        return json.dumps(payload, separators=(",", ":"))

    def get_book(self, order_depth: OrderDepth, history: List[float]) -> Optional[Dict[str, object]]:
        buy_levels = sorted(order_depth.buy_orders.items(), key=lambda item: item[0], reverse=True)
        sell_levels = sorted(((price, -volume) for price, volume in order_depth.sell_orders.items()), key=lambda item: item[0])
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

        recent_average = sum(history) / len(history) if history else mid
        momentum = mid - recent_average
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
            "momentum": float(momentum),
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

    def decay_fill_bias(self, value: float) -> float:
        return value * TOMATOES["POST_FILL_DECAY"]

    def current_book_snapshot(self, book: Dict[str, object]) -> Dict[str, List[List[int]]]:
        return {
            "buy": [[price, volume] for price, volume in book["buy_levels"][:3]],
            "sell": [[price, volume] for price, volume in book["sell_levels"][:3]],
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

    def realized_volatility(self, history: List[float], spread: int) -> float:
        if len(history) < 3:
            return max(1.0, spread / 2.0)
        diffs = [abs(history[index] - history[index - 1]) for index in range(1, len(history))]
        recent = diffs[-6:]
        return sum(recent) / max(1, len(recent))

    def multi_level_imbalance(self, book: Dict[str, object]) -> float:
        bid_total = 0.0
        ask_total = 0.0
        for index, (_price, volume) in enumerate(book["buy_levels"][:3]):
            bid_total += volume / (index + 1)
        for index, (_price, volume) in enumerate(book["sell_levels"][:3]):
            ask_total += volume / (index + 1)
        total = bid_total + ask_total
        if total <= 1e-9:
            return 0.0
        return (bid_total - ask_total) / total

    def order_flow_imbalance(self, previous_book: Dict[str, List[List[int]]], current_book: Dict[str, List[List[int]]]) -> float:
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
        return score / max(20.0, normalizer)

    def load_beta(self, memory: Dict[str, object], key: str = "beta") -> List[float]:
        raw = memory.get(key)
        if not isinstance(raw, list) or len(raw) != len(FEATURE_NAMES):
            return [0.0] * len(FEATURE_NAMES)
        return [float(value) if isinstance(value, (int, float)) else 0.0 for value in raw]

    def load_p_matrix(self, memory: Dict[str, object], key: str = "p_matrix") -> List[List[float]]:
        dimension = len(FEATURE_NAMES)
        fallback = [
            [TOMATOES["RLS_DELTA"] if row == col else 0.0 for col in range(dimension)]
            for row in range(dimension)
        ]
        raw = memory.get(key)
        if not isinstance(raw, list) or len(raw) != dimension:
            return fallback

        matrix: List[List[float]] = []
        for row, fallback_row in zip(raw, fallback):
            if not isinstance(row, list) or len(row) != dimension:
                matrix.append(fallback_row[:])
                continue
            matrix.append(
                [
                    float(value) if isinstance(value, (int, float)) else default
                    for value, default in zip(row, fallback_row)
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
        current_spread: float,
        current_toxic: float,
    ) -> Tuple[List[float], List[List[float]]]:
        if not isinstance(last_features, list) or len(last_features) != len(beta):
            return beta, p_matrix
        if not isinstance(last_mid, (int, float)):
            return beta, p_matrix
        if current_spread >= TOMATOES["RLS_SKIP_SPREAD"] or current_toxic >= TOMATOES["RLS_SKIP_TOXIC"]:
            return beta, p_matrix

        x = [float(value) for value in last_features]
        y = current_mid - float(last_mid)
        y = max(-TOMATOES["RLS_TARGET_CLIP"], min(TOMATOES["RLS_TARGET_CLIP"], y))
        dimension = len(beta)
        p_times_x = [
            sum(p_matrix[row][col] * x[col] for col in range(dimension))
            for row in range(dimension)
        ]
        denom = TOMATOES["RLS_LAMBDA"] + sum(x[index] * p_times_x[index] for index in range(dimension))
        if abs(denom) <= 1e-9:
            return beta, p_matrix

        k = [value / denom for value in p_times_x]
        prediction = sum(beta[index] * x[index] for index in range(dimension))
        error = y - prediction
        next_beta = [
            max(
                -TOMATOES["RLS_BETA_CLIP"],
                min(TOMATOES["RLS_BETA_CLIP"], beta[index] + (k[index] * error)),
            )
            for index in range(dimension)
        ]

        x_t_p = [
            sum(x[row] * p_matrix[row][col] for row in range(dimension))
            for col in range(dimension)
        ]
        next_matrix: List[List[float]] = []
        for row in range(dimension):
            next_row: List[float] = []
            for col in range(dimension):
                updated = (p_matrix[row][col] - (k[row] * x_t_p[col])) / TOMATOES["RLS_LAMBDA"]
                next_row.append(updated)
            next_matrix.append(next_row)

        return next_beta, next_matrix

    def update_post_fill_bias(
        self,
        state: TradingState,
        product: str,
        memory: Dict[str, object],
        current_mid: float,
    ) -> Tuple[float, float, int, List[Dict[str, float]]]:
        buy_bias = self.decay_fill_bias(float(memory.get("adverse_buy_bias", 0.0)))
        sell_bias = self.decay_fill_bias(float(memory.get("adverse_sell_bias", 0.0)))
        last_processed_ts = int(memory.get("last_fill_ts", -1))
        latest_ts = last_processed_ts
        pending_raw = memory.get("pending_fills", [])
        pending_fills: List[Dict[str, float]] = []
        if isinstance(pending_raw, list):
            for item in pending_raw:
                if isinstance(item, dict):
                    try:
                        pending_fills.append(
                            {
                                "side": str(item.get("side", "")),
                                "mid": float(item.get("mid", current_mid)),
                                "timestamp": float(item.get("timestamp", 0)),
                                "qty": float(item.get("qty", 1)),
                            }
                        )
                    except (TypeError, ValueError):
                        continue

        remaining_pending: List[Dict[str, float]] = []
        for fill in pending_fills:
            age = float(getattr(state, "timestamp", 0)) - fill["timestamp"]
            if age < TOMATOES["MARKOUT_DELAY_TICKS"]:
                remaining_pending.append(fill)
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
                    buy_bias = max(0.0, buy_bias - 0.5 * step)
            elif fill["side"] == "SELL":
                if markout > 0:
                    sell_bias = min(TOMATOES["POST_FILL_MAX_BIAS"], sell_bias + step)
                else:
                    sell_bias = max(0.0, sell_bias - 0.5 * step)

        for trade in state.own_trades.get(product, []):
            if not isinstance(trade, Trade):
                continue
            trade_ts = int(getattr(trade, "timestamp", -1))
            if trade_ts <= last_processed_ts:
                continue
            latest_ts = max(latest_ts, trade_ts)
            if getattr(trade, "buyer", None) == "SUBMISSION":
                remaining_pending.append(
                    {
                        "side": "BUY",
                        "mid": current_mid,
                        "timestamp": float(trade_ts),
                        "qty": float(max(1, abs(int(getattr(trade, "quantity", 0))))),
                    }
                )
            if getattr(trade, "seller", None) == "SUBMISSION":
                remaining_pending.append(
                    {
                        "side": "SELL",
                        "mid": current_mid,
                        "timestamp": float(trade_ts),
                        "qty": float(max(1, abs(int(getattr(trade, "quantity", 0))))),
                    }
                )

        return buy_bias, sell_bias, latest_ts, remaining_pending

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
        spread_norm = float(book["spread"]) / max(1.0, float(book["mid"]) / 1000.0)
        return [
            1.0,
            (float(book["micro"]) - float(book["mid"])) / spread_scale,
            float(book["l1_imbalance"]),
            ml_imbalance,
            ofi,
            float(book["momentum"]) / vol_scale,
            spread_norm,
        ]

    def predicted_delta(self, beta: List[float], features: List[float]) -> float:
        return sum(weight * value for weight, value in zip(beta, features))

    def regime_probabilities(
        self,
        alpha_signal: float,
        volatility: float,
        spread: int,
        ml_imbalance: float,
        ofi: float,
    ) -> Dict[str, float]:
        vol_scale = max(1.0, volatility)
        trend_signal = alpha_signal / vol_scale
        logits = {
            "trend_up": (
                TOMATOES["REGIME_TREND_COEF"] * trend_signal
                + TOMATOES["REGIME_FLOW_COEF"] * ofi
                + 0.45 * ml_imbalance
            ),
            "trend_down": (
                -TOMATOES["REGIME_TREND_COEF"] * trend_signal
                - TOMATOES["REGIME_FLOW_COEF"] * ofi
                - 0.45 * ml_imbalance
            ),
            "range": 0.35 - 0.90 * abs(trend_signal) - 0.35 * abs(ofi),
            "toxic": (
                TOMATOES["REGIME_TOXIC_COEF"] * (spread - TOMATOES["TOXIC_SPREAD"]) / 4.0
                + 0.90 * (volatility - TOMATOES["TOXIC_VOL"])
                + 0.80 * abs(ofi)
            ),
        }
        max_logit = max(logits.values())
        exps = {key: math.exp(value - max_logit) for key, value in logits.items()}
        total = sum(exps.values())
        return {key: value / total for key, value in exps.items()}

    def dynamic_soft_limit(self, regime: Dict[str, float], position_limit: int) -> int:
        ratio = (
            TOMATOES["SOFT_LIMIT_BASE"]
            + TOMATOES["SOFT_LIMIT_TREND_BONUS"] * max(regime["trend_up"], regime["trend_down"])
            - TOMATOES["SOFT_LIMIT_TOXIC_PENALTY"] * regime["toxic"]
        )
        ratio = max(0.20, min(0.72, ratio))
        return max(12, min(position_limit, int(position_limit * ratio)))

    def target_position(self, regime: Dict[str, float], alpha_signal: float, soft_limit: int) -> int:
        trend_bias = regime["trend_up"] - regime["trend_down"]
        alpha_bias = alpha_signal / max(2.5, abs(alpha_signal) + 2.5)
        target = round(soft_limit * (0.80 * trend_bias + 0.20 * alpha_bias))
        return max(-soft_limit, min(soft_limit, target))

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
        if regime["toxic"] >= 0.55:
            gamma = TOMATOES["AS_GAMMA_TOXIC"]
        elif max(regime["trend_up"], regime["trend_down"]) >= 0.55:
            gamma = TOMATOES["AS_GAMMA_TREND"]
        else:
            gamma = TOMATOES["AS_GAMMA_BASE"]
        inventory_gap = position - target_position
        return fair_value - (
            inventory_gap
            * gamma
            * max(0.8, volatility) ** 2
            * max(0.35, tau)
            * TOMATOES["AS_RES_SCALE"]
        )

    def quote_half_spread(
        self,
        book: Dict[str, object],
        position: int,
        soft_limit: int,
        volatility: float,
        maker_alpha: float,
        regime: Dict[str, float],
    ) -> float:
        spread = max(TOMATOES["QUOTE_EDGE"], float(book["spread"]) / 3.5)
        spread += TOMATOES["SPREAD_VOL_COEF"] * min(3.0, volatility)
        spread += TOMATOES["SPREAD_INV_COEF"] * min(1.0, abs(position) / max(1, soft_limit))
        spread += TOMATOES["SPREAD_TOXIC_COEF"] * regime["toxic"]
        spread -= TOMATOES["SPREAD_ALPHA_REBATE"] * min(1.0, abs(maker_alpha) / max(1.0, volatility))
        return max(TOMATOES["QUOTE_EDGE"], min(TOMATOES["MAX_QUOTE_EDGE"], spread))

    def passive_expected_value(
        self,
        side: str,
        quote: int,
        reservation: float,
        book: Dict[str, object],
        position: int,
        soft_limit: int,
        regime: Dict[str, float],
        adverse_bias: float,
    ) -> float:
        best_bid = int(book["best_bid"])
        best_ask = int(book["best_ask"])
        raw_capture = (reservation - quote) if side == "BUY" else (quote - reservation)
        spread_capture = max(0.0, raw_capture)

        queue_bonus = 0.0
        if side == "BUY" and quote == best_bid + 1:
            queue_bonus += TOMATOES["QUEUE_VALUE_COEF"]
        if side == "SELL" and quote == best_ask - 1:
            queue_bonus += TOMATOES["QUEUE_VALUE_COEF"]

        queue_depth = book["best_bid_volume"] if side == "BUY" else book["best_ask_volume"]
        p_fill = 0.20 + queue_bonus + 0.18 * max(0.0, 1.0 - (queue_depth / 35.0))
        p_fill = max(0.05, min(0.85, p_fill))

        adverse = (
            TOMATOES["PASSIVE_ADVERSE_COEF"] * regime["toxic"]
            + 0.25 * max(0.0, -raw_capture)
            + TOMATOES["POST_FILL_QUOTE_PENALTY"] * adverse_bias
        )
        inventory_cost = 0.15 * abs(position) / max(1, soft_limit)
        return (p_fill * spread_capture) - adverse - inventory_cost

    def maker_quotes(
        self,
        book: Dict[str, object],
        reservation: float,
        maker_alpha: float,
        builder: OrderBuilder,
        target_position: int,
        soft_limit: int,
        regime: Dict[str, float],
        buy_bias: float,
        sell_bias: float,
        volatility: float,
    ) -> Tuple[Optional[int], Optional[int]]:
        half_spread = self.quote_half_spread(
            book,
            builder.projected_position(),
            soft_limit,
            volatility,
            maker_alpha,
            regime,
        )
        buy_quote = math.floor(reservation - half_spread)
        sell_quote = math.ceil(reservation + half_spread)

        alpha_shift = 0
        if maker_alpha >= 0.8:
            alpha_shift = 1
        elif maker_alpha <= -0.8:
            alpha_shift = -1

        buy_quote += alpha_shift
        sell_quote += alpha_shift

        if buy_bias > 0.0:
            buy_quote -= int(math.ceil(buy_bias))
        if sell_bias > 0.0:
            sell_quote += int(math.ceil(sell_bias))

        if builder.projected_position() >= max(target_position, soft_limit):
            buy_quote -= 1
        if builder.projected_position() <= min(target_position, -soft_limit):
            sell_quote += 1

        return self.clamp_inside_spread(book, buy_quote, sell_quote)

    def passive_size(
        self,
        side: str,
        builder: OrderBuilder,
        target_position: int,
        soft_limit: int,
    ) -> int:
        size = TOMATOES["PASSIVE_SIZE"]
        projected = builder.projected_position()
        if side == "BUY":
            if projected < 0:
                size += 1
            if projected >= soft_limit:
                size = max(1, size - 3)
            if projected < target_position:
                size += 1
        else:
            if projected > 0:
                size += 1
            if projected <= -soft_limit:
                size = max(1, size - 3)
            if projected > target_position:
                size += 1
        return max(1, min(12, size))

    def take_edge(
        self,
        side: str,
        builder: OrderBuilder,
        target_position: int,
        taker_alpha: float,
        regime: Dict[str, float],
        adverse_bias: float,
    ) -> float:
        edge = TOMATOES["TAKE_EDGE"]
        edge += 0.35 * regime["toxic"]
        edge += TOMATOES["POST_FILL_TAKE_PENALTY"] * adverse_bias

        position_gap = builder.projected_position() - target_position
        if side == "BUY" and position_gap < 0:
            edge -= 0.20
        if side == "SELL" and position_gap > 0:
            edge -= 0.20

        if side == "BUY" and taker_alpha > 0:
            edge -= min(0.45, 0.12 * taker_alpha)
        if side == "SELL" and taker_alpha < 0:
            edge -= min(0.45, 0.12 * abs(taker_alpha))

        return max(0.40, edge)

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
            if side == "BUY":
                if price > fair_value - threshold or builder.buy_capacity <= 0:
                    break
                desired = max(0, min(soft_limit, max(target_position, 0)) - projected)
                if target_position <= projected < 0:
                    desired = max(desired, abs(projected))
                quantity = min(volume, builder.buy_capacity, TOMATOES["MAX_TAKE_SIZE"], max(0, desired))
                if quantity <= 0:
                    continue
                builder.add_buy(price, quantity)
                traded = True
            else:
                if price < fair_value + threshold or builder.sell_capacity <= 0:
                    break
                desired = max(0, projected - max(-soft_limit, min(target_position, 0)))
                if target_position >= projected > 0:
                    desired = max(desired, projected)
                quantity = min(volume, builder.sell_capacity, TOMATOES["MAX_TAKE_SIZE"], max(0, desired))
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
        order_depth = state.order_depths[product]
        product_history = history.get(product, [])
        book = self.get_book(order_depth, product_history)
        if book is None:
            return []

        product_history.append(float(book["mid"]))
        history[product] = product_history[-HISTORY_LENGTH:]

        builder = OrderBuilder(product, POSITION_LIMITS[product], state.position.get(product, 0))
        soft_limit = int(POSITION_LIMITS[product] * EMERALDS["SOFT_LIMIT_RATIO"])
        fair = (
            EMERALDS["REFERENCE_WEIGHT"] * EMERALDS["REFERENCE_PRICE"]
            + EMERALDS["MID_WEIGHT"] * float(book["mid"])
            + EMERALDS["MICRO_WEIGHT"] * float(book["micro"])
        )
        fair -= builder.projected_position() * EMERALDS["INVENTORY_SKEW"]

        best_ask = int(book["best_ask"])
        best_bid = int(book["best_bid"])
        ask_volume = int(book["best_ask_volume"])
        bid_volume = int(book["best_bid_volume"])

        buy_distance = fair - float(best_ask)
        sell_distance = float(best_bid) - fair

        buy_take_size = 0
        if buy_distance >= EMERALDS["TAKE_TIER_3_DISTANCE"]:
            buy_take_size = EMERALDS["TAKE_TIER_3_SIZE"]
        elif buy_distance >= EMERALDS["TAKE_TIER_2_DISTANCE"]:
            buy_take_size = EMERALDS["TAKE_TIER_2_SIZE"]
        elif buy_distance >= EMERALDS["TAKE_TIER_1_DISTANCE"]:
            buy_take_size = EMERALDS["TAKE_TIER_1_SIZE"]

        sell_take_size = 0
        if sell_distance >= EMERALDS["TAKE_TIER_3_DISTANCE"]:
            sell_take_size = EMERALDS["TAKE_TIER_3_SIZE"]
        elif sell_distance >= EMERALDS["TAKE_TIER_2_DISTANCE"]:
            sell_take_size = EMERALDS["TAKE_TIER_2_SIZE"]
        elif sell_distance >= EMERALDS["TAKE_TIER_1_DISTANCE"]:
            sell_take_size = EMERALDS["TAKE_TIER_1_SIZE"]

        projected = builder.projected_position()
        if projected <= -soft_limit:
            buy_take_size += 4
            sell_take_size = max(0, sell_take_size - 3)
        elif projected >= soft_limit:
            sell_take_size += 4
            buy_take_size = max(0, buy_take_size - 3)

        if buy_take_size > 0 and builder.buy_capacity > 0:
            builder.add_buy(best_ask, min(ask_volume, buy_take_size))
        if sell_take_size > 0 and builder.sell_capacity > 0:
            builder.add_sell(best_bid, min(bid_volume, sell_take_size))

        projected = builder.projected_position()
        if (
            projected > 0
            and builder.sell_capacity > 0
            and best_bid >= math.ceil(fair + EMERALDS["CLEAR_WIDTH"])
        ):
            builder.add_sell(best_bid, min(projected, bid_volume, EMERALDS["BASE_ORDER_SIZE"]))

        projected = builder.projected_position()
        if (
            projected < 0
            and builder.buy_capacity > 0
            and best_ask <= math.floor(fair - EMERALDS["CLEAR_WIDTH"])
        ):
            builder.add_buy(best_ask, min(abs(projected), ask_volume, EMERALDS["BASE_ORDER_SIZE"]))

        projected = builder.projected_position()
        buy_quote = round(fair - EMERALDS["DEFAULT_EDGE"])
        sell_quote = round(fair + EMERALDS["DEFAULT_EDGE"])

        asks_above_fair = [
            price for price, _volume in book["sell_levels"]
            if price > fair + EMERALDS["DISREGARD_EDGE"]
        ]
        bids_below_fair = [
            price for price, _volume in book["buy_levels"]
            if price < fair - EMERALDS["DISREGARD_EDGE"]
        ]

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

        if projected >= soft_limit:
            buy_quote -= 1
            sell_quote -= 1
        elif projected <= -soft_limit:
            buy_quote += 1
            sell_quote += 1

        buy_quote, sell_quote = self.clamp_inside_spread(book, buy_quote, sell_quote)

        if buy_quote is not None and builder.buy_capacity > 0 and projected < soft_limit + EMERALDS["BASE_ORDER_SIZE"]:
            size = EMERALDS["BASE_ORDER_SIZE"]
            if int(book["spread"]) >= 16:
                size += 1
            if projected <= -soft_limit:
                size += 4
            elif projected >= soft_limit:
                size = max(1, size - 6)
            builder.add_buy(buy_quote, size)

        projected = builder.projected_position()
        if sell_quote is not None and builder.sell_capacity > 0 and projected > -(soft_limit + EMERALDS["BASE_ORDER_SIZE"]):
            size = EMERALDS["BASE_ORDER_SIZE"]
            if int(book["spread"]) >= 16:
                size += 1
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
        order_depth = state.order_depths[product]
        product_history = history.get(product, [])
        book = self.get_book(order_depth, product_history)
        if book is None:
            return [], memory

        previous_book = self.previous_book_snapshot(memory)
        current_book = self.current_book_snapshot(book)
        ml_imbalance = self.multi_level_imbalance(book)
        ofi = self.order_flow_imbalance(previous_book, current_book)
        volatility = self.realized_volatility(product_history, int(book["spread"]))
        prelim_regime = self.regime_probabilities(0.0, volatility, int(book["spread"]), ml_imbalance, ofi)

        beta = self.load_beta(memory)
        p_matrix = self.load_p_matrix(memory)
        beta, p_matrix = self.update_rls(
            beta,
            p_matrix,
            memory.get("last_features"),
            memory.get("last_mid"),
            float(book["mid"]),
            float(book["spread"]),
            prelim_regime["toxic"],
        )

        buy_bias, sell_bias, last_fill_ts, pending_fills = self.update_post_fill_bias(
            state,
            product,
            memory,
            float(book["mid"]),
        )

        features = self.feature_vector(book, product_history, ml_imbalance, ofi, volatility)
        online_delta = self.predicted_delta(beta, features)
        residual_alpha = (
            TOMATOES["OFI_WEIGHT"] * ofi
            + TOMATOES["ML_IMBALANCE_WEIGHT"] * ml_imbalance
            + 0.20 * ((float(book["micro"]) - float(book["mid"])) / max(1.0, float(book["spread"])))
        )
        maker_alpha = TOMATOES["MAKER_ALPHA_SCALE"] * (
            online_delta + TOMATOES["RESIDUAL_ALPHA_WEIGHT"] * residual_alpha
        )
        taker_alpha = TOMATOES["TAKER_ALPHA_SCALE"] * (
            online_delta
            + TOMATOES["RESIDUAL_ALPHA_WEIGHT"] * residual_alpha
            + TOMATOES["MOMENTUM_RESIDUAL_WEIGHT"] * (float(book["momentum"]) / max(1.0, volatility))
        )
        regime = self.regime_probabilities(taker_alpha, volatility, int(book["spread"]), ml_imbalance, ofi)

        soft_limit = self.dynamic_soft_limit(regime, POSITION_LIMITS[product])
        position = state.position.get(product, 0)
        target_position = self.target_position(regime, taker_alpha, soft_limit)
        tau = self.time_fraction_remaining(state)

        base_fair = (
            float(book["mid"])
            + 0.35 * (float(book["micro"]) - float(book["mid"]))
            + 0.10 * (float(book["recent_average"]) - float(book["mid"]))
            + maker_alpha
        )
        base_fair -= position * TOMATOES["INVENTORY_SKEW"]
        reservation = self.reservation_price(base_fair, position, target_position, volatility, tau, regime)
        taker_fair = float(book["mid"]) + taker_alpha

        builder = OrderBuilder(product, POSITION_LIMITS[product], position)

        buy_threshold = self.take_edge("BUY", builder, target_position, taker_alpha, regime, buy_bias)
        sell_threshold = self.take_edge("SELL", builder, target_position, taker_alpha, regime, sell_bias)
        took_buy = self.sweep_book("BUY", book, builder, taker_fair, buy_threshold, target_position, soft_limit)
        took_sell = self.sweep_book("SELL", book, builder, taker_fair, sell_threshold, target_position, soft_limit)

        buy_quote, sell_quote = self.maker_quotes(
            book,
            reservation,
            maker_alpha,
            builder,
            target_position,
            soft_limit,
            regime,
            buy_bias,
            sell_bias,
            volatility,
        )

        if buy_quote is not None and builder.buy_capacity > 0 and builder.projected_position() < soft_limit:
            buy_ev = self.passive_expected_value(
                "BUY",
                buy_quote,
                reservation,
                book,
                builder.projected_position(),
                soft_limit,
                regime,
                buy_bias,
            )
            if buy_ev >= TOMATOES["PASSIVE_MIN_EV"] and (not took_buy or builder.projected_position() < target_position):
                quantity = min(
                    self.passive_size("BUY", builder, target_position, soft_limit),
                    builder.buy_capacity,
                )
                if builder.projected_position() < target_position:
                    quantity = min(quantity, max(1, target_position - builder.projected_position()))
                builder.add_buy(buy_quote, quantity)

        if sell_quote is not None and builder.sell_capacity > 0 and builder.projected_position() > -soft_limit:
            sell_ev = self.passive_expected_value(
                "SELL",
                sell_quote,
                reservation,
                book,
                builder.projected_position(),
                soft_limit,
                regime,
                sell_bias,
            )
            if sell_ev >= TOMATOES["PASSIVE_MIN_EV"] and (not took_sell or builder.projected_position() > target_position):
                quantity = min(
                    self.passive_size("SELL", builder, target_position, soft_limit),
                    builder.sell_capacity,
                )
                if builder.projected_position() > target_position:
                    quantity = min(quantity, max(1, builder.projected_position() - target_position))
                builder.add_sell(sell_quote, quantity)

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
            "last_fill_ts": last_fill_ts,
            "pending_fills": pending_fills,
        }
        return builder.orders, next_memory

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        mid_history, memory = self.load_trader_data(state.traderData)
        next_memory: Dict[str, Dict[str, object]] = dict(memory)

        for product, order_depth in state.order_depths.items():
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
