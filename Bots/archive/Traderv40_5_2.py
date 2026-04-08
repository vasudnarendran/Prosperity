from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


DEFAULT_EMERALDS_PARAMS = {
    "REFERENCE_PRICE": 10000.0,
    "REFERENCE_WEIGHT": 0.8,
    "MID_WEIGHT": 0.2,
    "MICRO_WEIGHT": 0.00,
    "INVENTORY_SKEW": 0.0328922991,
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
    "SOFT_LIMIT_RATIO": 0.6357999832,
}


DEFAULT_TOMATOES_PARAMS = {
    "MID_WEIGHT": 0.25,
    "MICRO_WEIGHT": 0.30,
    "HISTORY_WEIGHT": 0.25,
    "REGRESSION_WEIGHT": 0.20,
    "IMBALANCE_WEIGHT": 0.35,
    "INVENTORY_RESERVATION_SKEW": 0.007,
    "SIZE_INVENTORY_PRESSURE": 0.28,
    "BASE_TAKE_EDGE": 0.72,
    "BASE_QUOTE_EDGE": 2.45,
    "PASSIVE_SIZE": 9,
    "MAX_TAKE_SIZE": 10,
    "REGRESSION_WINDOW": 8,
    "REGRESSION_HORIZON": 0.5,
    "TREND_ENTRY_THRESHOLD": 0.82,
    "FIT_THRESHOLD": 0.45,
    "TOXIC_SPREAD_THRESHOLD": 15.0,
    "TOXIC_VOL_THRESHOLD": 3.2,
    "REGIME_SMOOTH_ALPHA": 0.26,
    "SOFT_LIMIT_RATIO": 0.56828726,
    "TARGET_TREND_RATIO": 0.72,
    "TARGET_RANGE_RATIO": 0.14,
    "TARGET_STRETCH_DAMP": 0.14,
    "TIME_HORIZON_TICKS": 10000.0,
    "LATE_FLATTEN_START": 0.10,
    "LATE_FLATTEN_HARD": 0.04,
    "QUOTE_VOL_COEF": 0.08,
    "QUOTE_TOXIC_COEF": 0.85,
    "QUOTE_FEEDBACK_COEF": 0.12,
    "QUOTE_TREND_SKEW": 0.22,
    "TAKE_TREND_REWARD": 0.38,
    "TAKE_TOXIC_PENALTY": 0.16,
    "TAKE_FEEDBACK_PENALTY": 0.14,
    "ALPHA_EDGE_SCALE": 1.4153631,
    "ALPHA_IMBALANCE_SCALE": 0.7,
    "ALPHA_REFERENCE_WEIGHT": 0.45,
    "ALPHA_MID_WEIGHT": 0.20,
    "ALPHA_MICRO_WEIGHT": 0.25,
    "ALPHA_FLOW_WEIGHT": 0.10,
    "ALPHA_FLOW_SPREAD_SCALE": 0.50,
    "ALPHA_BLEND_WEIGHT": 0.28,
    "FAIR_ALPHA_WEIGHT": 0.42,
    "ALPHA_CAP": 2.20,
    "RANGE_ALPHA_DAMP": 0.55,
    "CONFLICT_ALPHA_DAMP": 0.55,
    "MOMENTUM_ALPHA_DAMP": 0.8,
    "POSITION_ALPHA_DAMP_START": 14.0,
    "POSITION_ALPHA_DAMP_END": 28.0,
    "MARKOUT_DELAY_TICKS": 400,
    "FEEDBACK_EWMA_ALPHA": 0.18,
    "GOOD_FILL_BONUS": 0.07,
    "BAD_FILL_PENALTY": 0.14,
}


class BaseProductTrader:
    HISTORY_LENGTH = 8

    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
        memory: Optional[Dict[str, object]] = None,
    ) -> None:
        self.product = product
        self.state = state
        self.mid_history = mid_history
        self.position_limit = position_limit
        self.memory: Dict[str, object] = dict(memory) if isinstance(memory, dict) else {}
        self.orders: List[Order] = []

        self.order_depth: Optional[OrderDepth] = state.order_depths.get(product)
        self.position = state.position.get(product, 0)
        self.buy_capacity = position_limit - self.position
        self.sell_capacity = position_limit + self.position
        self.soft_limit = int(position_limit * 0.55)

        self.buy_levels: List[Tuple[int, int]] = []
        self.sell_levels: List[Tuple[int, int]] = []
        self.best_bid: Optional[int] = None
        self.best_ask: Optional[int] = None
        self.best_bid_volume = 0
        self.best_ask_volume = 0
        self.mid: Optional[float] = None
        self.micro: Optional[float] = None
        self.spread: Optional[int] = None
        self.recent_average: Optional[float] = None
        self.momentum: float = 0.0
        self.imbalance: float = 0.0

        self._load_market_state()

    def _load_market_state(self) -> None:
        if self.order_depth is None:
            return

        self.buy_levels = sorted(
            self.order_depth.buy_orders.items(),
            key=lambda item: item[0],
            reverse=True,
        )
        self.sell_levels = sorted(
            ((price, -volume) for price, volume in self.order_depth.sell_orders.items()),
            key=lambda item: item[0],
        )

        self.best_bid = self.buy_levels[0][0] if self.buy_levels else None
        self.best_ask = self.sell_levels[0][0] if self.sell_levels else None
        if self.best_bid is None or self.best_ask is None:
            return

        self.best_bid_volume = self.buy_levels[0][1]
        self.best_ask_volume = self.sell_levels[0][1]
        self.mid = (self.best_bid + self.best_ask) / 2
        self.spread = self.best_ask - self.best_bid

        total_top_volume = self.best_bid_volume + self.best_ask_volume
        if total_top_volume > 0:
            self.micro = (
                (self.best_bid * self.best_ask_volume) + (self.best_ask * self.best_bid_volume)
            ) / total_top_volume
            self.imbalance = (self.best_bid_volume - self.best_ask_volume) / total_top_volume
        else:
            self.micro = self.mid
            self.imbalance = 0.0

        history = self.mid_history.get(self.product, [])
        self.recent_average = sum(history) / len(history) if history else self.mid
        self.momentum = self.mid - self.recent_average

        history.append(self.mid)
        self.mid_history[self.product] = history[-self.HISTORY_LENGTH :]

    def has_book(self) -> bool:
        return self.best_bid is not None and self.best_ask is not None and self.mid is not None and self.micro is not None

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

    def apply_parameter_overrides(
        self,
        defaults: Dict[str, float],
        overrides: Optional[Dict[str, float]],
    ) -> None:
        for key, value in defaults.items():
            setattr(self, key, value)

        if not overrides:
            return

        for key, value in overrides.items():
            if key in defaults and isinstance(value, (int, float)):
                setattr(self, key, float(value))

    def clamp_inside_spread(
        self,
        buy_quote: Optional[int],
        sell_quote: Optional[int],
    ) -> Tuple[Optional[int], Optional[int]]:
        if not self.has_book():
            return None, None

        best_bid = int(self.best_bid)
        best_ask = int(self.best_ask)

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

    def run(self) -> List[Order]:
        return self.orders

    def export_memory(self) -> Dict[str, object]:
        return self.memory


class EmeraldsTrader(BaseProductTrader):
    PARAMETER_DEFAULTS = DEFAULT_EMERALDS_PARAMS

    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
        memory: Optional[Dict[str, object]] = None,
        params: Optional[Dict[str, float]] = None,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit, memory)
        self.apply_parameter_overrides(self.PARAMETER_DEFAULTS, params)
        self.soft_limit = int(position_limit * self.SOFT_LIMIT_RATIO)

    def fair_value(self) -> float:
        return (
            self.REFERENCE_WEIGHT * self.REFERENCE_PRICE
            + self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
        )

    def adjusted_fair_value(self) -> float:
        return self.fair_value() - (self.projected_position() * self.INVENTORY_SKEW)

    def take_size_for_distance(self, distance: float) -> int:
        if distance >= self.TAKE_TIER_3_DISTANCE:
            return int(self.TAKE_TIER_3_SIZE)
        if distance >= self.TAKE_TIER_2_DISTANCE:
            return int(self.TAKE_TIER_2_SIZE)
        if distance >= self.TAKE_TIER_1_DISTANCE:
            return int(self.TAKE_TIER_1_SIZE)
        return 0

    def tiered_take_size(self, side: str, adjusted_fair: float) -> int:
        if side == "BUY":
            distance = adjusted_fair - float(self.best_ask)
        else:
            distance = float(self.best_bid) - adjusted_fair

        size = self.take_size_for_distance(distance)
        position = self.projected_position()

        if side == "BUY":
            if position <= -self.soft_limit:
                size += 4
            elif position >= self.soft_limit:
                size = max(0, size - 3)
        else:
            if position >= self.soft_limit:
                size += 4
            elif position <= -self.soft_limit:
                size = max(0, size - 3)

        return min(self.position_limit, size)

    def clear_orders(self, adjusted_fair: float) -> Tuple[bool, bool]:
        cleared_buy = False
        cleared_sell = False
        position = self.projected_position()

        if (
            position > 0
            and self.sell_capacity > 0
            and int(self.best_bid) >= math.ceil(adjusted_fair + self.CLEAR_WIDTH)
        ):
            before = self.sell_capacity
            quantity = min(position, self.best_bid_volume, int(self.BASE_ORDER_SIZE))
            self.add_sell(int(self.best_bid), quantity)
            cleared_sell = self.sell_capacity < before

        position = self.projected_position()
        if (
            position < 0
            and self.buy_capacity > 0
            and int(self.best_ask) <= math.floor(adjusted_fair - self.CLEAR_WIDTH)
        ):
            before = self.buy_capacity
            quantity = min(abs(position), self.best_ask_volume, int(self.BASE_ORDER_SIZE))
            self.add_buy(int(self.best_ask), quantity)
            cleared_buy = self.buy_capacity < before

        return cleared_buy, cleared_sell

    def passive_quotes(self, adjusted_fair: float) -> Tuple[Optional[int], Optional[int]]:
        asks_above_fair = [
            price for price, _volume in self.sell_levels
            if price > adjusted_fair + self.DISREGARD_EDGE
        ]
        bids_below_fair = [
            price for price, _volume in self.buy_levels
            if price < adjusted_fair - self.DISREGARD_EDGE
        ]

        buy_quote = round(adjusted_fair - self.DEFAULT_EDGE)
        sell_quote = round(adjusted_fair + self.DEFAULT_EDGE)

        best_ask_above_fair = min(asks_above_fair) if asks_above_fair else None
        best_bid_below_fair = max(bids_below_fair) if bids_below_fair else None

        if best_ask_above_fair is not None:
            if abs(best_ask_above_fair - adjusted_fair) <= self.JOIN_EDGE:
                sell_quote = best_ask_above_fair
            else:
                sell_quote = best_ask_above_fair - 1

        if best_bid_below_fair is not None:
            if abs(adjusted_fair - best_bid_below_fair) <= self.JOIN_EDGE:
                buy_quote = best_bid_below_fair
            else:
                buy_quote = best_bid_below_fair + 1

        position = self.projected_position()
        if position >= self.soft_limit:
            sell_quote -= 1
            buy_quote -= 1
        elif position <= -self.soft_limit:
            buy_quote += 1
            sell_quote += 1

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def passive_size(self, side: str) -> int:
        size = int(self.BASE_ORDER_SIZE)
        if int(self.spread) >= 16:
            size += 1

        position = self.projected_position()
        if side == "BUY":
            if position <= -self.soft_limit:
                size += 4
            elif position >= self.soft_limit:
                size = max(1, size - 6)
        else:
            if position >= self.soft_limit:
                size += 4
            elif position <= -self.soft_limit:
                size = max(1, size - 6)

        return max(1, size)

    def take_orders(self, adjusted_fair: float) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        buy_take_size = self.tiered_take_size("BUY", adjusted_fair)
        if buy_take_size > 0 and self.buy_capacity > 0:
            before = self.buy_capacity
            self.add_buy(int(self.best_ask), min(self.best_ask_volume, buy_take_size))
            took_buy = self.buy_capacity < before

        sell_take_size = self.tiered_take_size("SELL", adjusted_fair)
        if sell_take_size > 0 and self.sell_capacity > 0:
            before = self.sell_capacity
            self.add_sell(int(self.best_bid), min(self.best_bid_volume, sell_take_size))
            took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        adjusted_fair = self.adjusted_fair_value()
        took_buy, took_sell = self.take_orders(adjusted_fair)
        cleared_buy, cleared_sell = self.clear_orders(adjusted_fair)
        buy_quote, sell_quote = self.passive_quotes(adjusted_fair)
        position = self.projected_position()

        if (
            not took_buy
            and not cleared_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and position < self.soft_limit + int(self.BASE_ORDER_SIZE)
        ):
            self.add_buy(buy_quote, self.passive_size("BUY"))

        if (
            not took_sell
            and not cleared_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and position > -(self.soft_limit + int(self.BASE_ORDER_SIZE))
        ):
            self.add_sell(sell_quote, self.passive_size("SELL"))

        return self.orders


class TomatoesTrader(BaseProductTrader):
    PARAMETER_DEFAULTS = DEFAULT_TOMATOES_PARAMS

    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
        memory: Optional[Dict[str, object]] = None,
        params: Optional[Dict[str, float]] = None,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit, memory)
        self.apply_parameter_overrides(self.PARAMETER_DEFAULTS, params)
        self.soft_limit = int(position_limit * self.SOFT_LIMIT_RATIO)
        self.fill_quality_ewma = float(self.memory.get("fill_quality_ewma", 0.0))
        self.adverse_ewma = float(self.memory.get("adverse_ewma", 0.0))
        self.trend_score = float(self.memory.get("trend_score", 0.0))
        self.toxic_score = max(0.0, float(self.memory.get("toxic_score", 0.0)))
        pending = self.memory.get("pending_fills", [])
        self.pending_fills: List[Dict[str, float]] = []
        if isinstance(pending, list):
            for item in pending:
                if isinstance(item, dict):
                    try:
                        self.pending_fills.append(
                            {
                                "timestamp": float(item.get("timestamp", 0.0)),
                                "price": float(item.get("price", 0.0)),
                                "side": float(item.get("side", 0.0)),
                                "qty": float(item.get("qty", 0.0)),
                            }
                        )
                    except (TypeError, ValueError):
                        continue
        seen_raw = self.memory.get("seen_trade_keys", [])
        self.seen_trade_keys = [str(value) for value in seen_raw[-24:]] if isinstance(seen_raw, list) else []

    def regression_metrics(self) -> Tuple[float, float, float, float]:
        history = self.mid_history.get(self.product, [])
        window = history[-int(self.REGRESSION_WINDOW) :]
        if len(window) < 2:
            return float(self.mid), float(self.mid), 0.0, 0.0

        n = len(window)
        x_mean = (n - 1) / 2.0
        y_mean = sum(window) / n
        var_x = sum((index - x_mean) ** 2 for index in range(n))
        cov_xy = sum((index - x_mean) * (price - y_mean) for index, price in enumerate(window))
        slope = cov_xy / var_x if var_x else 0.0
        intercept = y_mean - slope * x_mean

        fitted = [intercept + slope * index for index in range(n)]
        predicted_now = fitted[-1]
        predicted_next = intercept + slope * ((n - 1) + self.REGRESSION_HORIZON)

        ss_tot = sum((price - y_mean) ** 2 for price in window)
        ss_res = sum((price - fit) ** 2 for price, fit in zip(window, fitted))
        fit_quality = 0.0 if ss_tot <= 1e-9 else max(0.0, min(1.0, 1.0 - (ss_res / ss_tot)))

        diffs = [abs(window[index] - window[index - 1]) for index in range(1, n)]
        volatility = sum(diffs) / len(diffs) if diffs else 0.0
        return predicted_now, predicted_next, fit_quality, volatility

    def time_fraction_remaining(self) -> float:
        timestamp = float(getattr(self.state, "timestamp", 0))
        remaining_ticks = max(0.0, self.TIME_HORIZON_TICKS - (timestamp / 100.0))
        return remaining_ticks / self.TIME_HORIZON_TICKS

    def _trade_key(self, trade: object) -> str:
        timestamp = int(getattr(trade, "timestamp", -1))
        price = int(getattr(trade, "price", 0))
        quantity = int(getattr(trade, "quantity", 0))
        buyer = "1" if getattr(trade, "buyer", None) == "SUBMISSION" else "0"
        seller = "1" if getattr(trade, "seller", None) == "SUBMISSION" else "0"
        return f"{timestamp}:{price}:{quantity}:{buyer}:{seller}"

    def update_fill_feedback(self) -> None:
        current_ts = float(getattr(self.state, "timestamp", 0))
        spread_scale = max(1.0, float(self.spread) / 2.0)
        still_pending: List[Dict[str, float]] = []
        for fill in self.pending_fills:
            if current_ts - fill["timestamp"] < self.MARKOUT_DELAY_TICKS:
                still_pending.append(fill)
                continue
            signed_markout = (float(self.mid) - fill["price"]) * fill["side"]
            scaled_markout = max(-2.0, min(2.0, signed_markout / spread_scale))
            self.fill_quality_ewma = (
                (1.0 - self.FEEDBACK_EWMA_ALPHA) * self.fill_quality_ewma
                + self.FEEDBACK_EWMA_ALPHA * scaled_markout
            )
            adverse_obs = 1.0 if signed_markout < -0.5 else 0.0
            self.adverse_ewma = (
                (1.0 - self.FEEDBACK_EWMA_ALPHA) * self.adverse_ewma
                + self.FEEDBACK_EWMA_ALPHA * adverse_obs
            )
        self.pending_fills = still_pending

        for trade in self.state.own_trades.get(self.product, []):
            key = self._trade_key(trade)
            if key in self.seen_trade_keys:
                continue
            self.seen_trade_keys.append(key)
            quantity = max(1, abs(int(getattr(trade, "quantity", 0))))
            if getattr(trade, "buyer", None) == "SUBMISSION":
                side = 1.0
            elif getattr(trade, "seller", None) == "SUBMISSION":
                side = -1.0
            else:
                continue
            self.pending_fills.append(
                {
                    "timestamp": float(getattr(trade, "timestamp", 0)),
                    "price": float(getattr(trade, "price", 0)),
                    "side": side,
                    "qty": float(quantity),
                }
            )
        self.seen_trade_keys = self.seen_trade_keys[-24:]

    def inventory_pressure(self, side: Optional[str] = None) -> float:
        position = self.projected_position()
        ratio = min(1.25, abs(position) / max(1, self.soft_limit))
        if side is None:
            return ratio
        if side == "BUY" and position <= 0:
            return 0.25 * ratio
        if side == "SELL" and position >= 0:
            return 0.25 * ratio
        return ratio

    def smooth_score(self, previous: float, current: float) -> float:
        alpha = self.REGIME_SMOOTH_ALPHA
        if previous * current < 0:
            alpha = max(0.16, alpha - 0.06)
        return ((1.0 - alpha) * previous) + (alpha * current)

    def hybrid_alpha(self) -> Tuple[float, float]:
        reference_price = float(self.recent_average)
        half_spread = max(1.0, float(self.spread) / 2.0)
        flow_signal = self.imbalance * half_spread * self.ALPHA_FLOW_SPREAD_SCALE
        hybrid_fair = (
            self.ALPHA_REFERENCE_WEIGHT * reference_price
            + self.ALPHA_MID_WEIGHT * float(self.mid)
            + self.ALPHA_MICRO_WEIGHT * float(self.micro)
            + self.ALPHA_FLOW_WEIGHT * (float(self.mid) + flow_signal)
        )
        alpha = hybrid_fair - float(self.mid)
        alpha = max(-self.ALPHA_CAP, min(self.ALPHA_CAP, alpha))
        return hybrid_fair, alpha

    def guarded_hybrid_alpha(self, hybrid_alpha: float, regression_edge: float, state_name: str) -> float:
        weight = 1.0
        if state_name == "range":
            weight *= self.RANGE_ALPHA_DAMP

        if hybrid_alpha * regression_edge < 0:
            weight *= self.CONFLICT_ALPHA_DAMP

        if hybrid_alpha * self.imbalance < 0:
            weight *= self.CONFLICT_ALPHA_DAMP

        if hybrid_alpha * self.momentum < 0:
            weight *= self.MOMENTUM_ALPHA_DAMP

        position = self.projected_position()
        if hybrid_alpha * position > 0:
            abs_pos = abs(position)
            if abs_pos >= self.POSITION_ALPHA_DAMP_START:
                if abs_pos >= self.POSITION_ALPHA_DAMP_END:
                    weight *= 0.0
                else:
                    span = self.POSITION_ALPHA_DAMP_END - self.POSITION_ALPHA_DAMP_START
                    ratio = (abs_pos - self.POSITION_ALPHA_DAMP_START) / max(1e-9, span)
                    weight *= max(0.0, 1.0 - ratio)

        return hybrid_alpha * weight

    def classify_state(self, fit_quality: float) -> str:
        if self.time_fraction_remaining() <= self.LATE_FLATTEN_HARD and abs(self.projected_position()) > 0:
            return "flatten"
        if self.toxic_score >= 0.95:
            return "volatile"
        if (
            self.trend_score >= self.TREND_ENTRY_THRESHOLD
            and fit_quality >= self.FIT_THRESHOLD
            and self.imbalance >= -0.02
        ):
            return "trend_up"
        if (
            self.trend_score <= -self.TREND_ENTRY_THRESHOLD
            and fit_quality >= self.FIT_THRESHOLD
            and self.imbalance <= 0.02
        ):
            return "trend_down"
        return "range"

    def target_position(self, state_name: str, predicted_edge: float) -> int:
        tau = self.time_fraction_remaining()
        stretch = (float(self.mid) - float(self.recent_average)) / max(1.0, abs(predicted_edge) + 1.0)
        if state_name == "flatten":
            return 0
        if state_name == "volatile":
            return 0
        if state_name in {"trend_up", "trend_down"}:
            conviction = clip(abs(self.trend_score) / max(self.TREND_ENTRY_THRESHOLD, 1.0), 0.45, 1.0)
            target = int(round(self.soft_limit * self.TARGET_TREND_RATIO * conviction))
            target = int(round(target * max(0.65, 1.0 - self.TARGET_STRETCH_DAMP * max(0.0, abs(stretch) - 1.2))))
            if tau <= self.LATE_FLATTEN_START:
                target = int(round(target * max(0.35, tau / self.LATE_FLATTEN_START)))
            return target if state_name == "trend_up" else -target

        range_target = -int(round(self.soft_limit * self.TARGET_RANGE_RATIO * clip(stretch, -1.0, 1.0)))
        if tau <= self.LATE_FLATTEN_START:
            range_target = int(round(range_target * max(0.25, tau / self.LATE_FLATTEN_START)))
        return range_target

    def toxicity(self, volatility: float) -> float:
        score = 0.0
        if volatility >= 2.0:
            score += 0.5
        if abs(self.imbalance) >= 0.45:
            score += 0.5
        return score

    def fill_bias(self) -> float:
        return clip(self.fill_quality_ewma - self.adverse_ewma, -1.0, 1.0)

    def fair_value(
        self,
        state_name: str,
        target_position: int,
        predicted_now: float,
        predicted_next: float,
        hybrid_alpha: float,
        volatility: float,
    ) -> float:
        line_gap = predicted_now - float(self.mid)
        scaled_imbalance = self.imbalance * self.ALPHA_IMBALANCE_SCALE
        fair = (
            self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
            + self.HISTORY_WEIGHT * float(self.recent_average)
            + self.REGRESSION_WEIGHT * predicted_next
            + self.IMBALANCE_WEIGHT * scaled_imbalance
        )
        fair += self.FAIR_ALPHA_WEIGHT * hybrid_alpha
        if state_name == "range":
            fair += 0.12 * line_gap
        else:
            fair += 0.22 * (predicted_next - float(self.mid))

        inventory_gap = self.projected_position() - target_position
        reservation_shift = inventory_gap * self.INVENTORY_RESERVATION_SKEW * max(1.0, volatility)
        if self.time_fraction_remaining() <= self.LATE_FLATTEN_START:
            reservation_shift *= 1.35
        return fair - reservation_shift

    def take_edge(
        self,
        side: str,
        state_name: str,
        predicted_edge: float,
        volatility: float,
    ) -> float:
        edge = self.BASE_TAKE_EDGE
        edge += self.TAKE_TOXIC_PENALTY * self.toxic_score
        edge += self.TAKE_FEEDBACK_PENALTY * max(0.0, self.adverse_ewma - 0.30)
        edge -= self.GOOD_FILL_BONUS * max(0.0, self.fill_quality_ewma)

        if side == "BUY" and state_name == "trend_up":
            edge -= self.TAKE_TREND_REWARD
        elif side == "SELL" and state_name == "trend_down":
            edge -= self.TAKE_TREND_REWARD

        if state_name == "range":
            edge += 0.02
        if state_name == "flatten":
            edge -= 0.10
        if self.time_fraction_remaining() <= self.LATE_FLATTEN_HARD and side == ("SELL" if self.projected_position() > 0 else "BUY"):
            edge -= 0.18

        if predicted_edge > 0 and side == "BUY":
            edge -= min(0.22, 0.06 * predicted_edge)
        elif predicted_edge < 0 and side == "SELL":
            edge -= min(0.22, 0.06 * abs(predicted_edge))
        return max(0.45, edge)

    def quote_edge(self, state_name: str, volatility: float) -> float:
        edge = max(self.BASE_QUOTE_EDGE, float(self.spread) / 3.5)
        edge += self.QUOTE_VOL_COEF * min(3.0, volatility)
        edge += self.QUOTE_TOXIC_COEF * self.toxic_score
        edge += self.QUOTE_FEEDBACK_COEF * max(0.0, self.adverse_ewma - 0.25)
        edge += 0.30 * self.inventory_pressure()
        if state_name == "range" and self.toxic_score < 0.25 and self.inventory_pressure() < 0.25:
            edge -= 0.12
        if state_name == "volatile":
            edge += 0.60
        if state_name == "flatten":
            edge += 0.35
        return clip(edge, 1.2, 8.0)

    def passive_quotes(
        self,
        reservation_price: float,
        state_name: str,
        target_position: int,
        predicted_edge: float,
        volatility: float,
    ) -> Tuple[Optional[int], Optional[int]]:
        quote_edge = self.quote_edge(state_name, volatility)
        center = reservation_price
        if state_name == "trend_up":
            center += self.QUOTE_TREND_SKEW * clip(predicted_edge / max(1.0, self.TREND_ENTRY_THRESHOLD), 0.0, 1.0)
        elif state_name == "trend_down":
            center -= self.QUOTE_TREND_SKEW * clip(abs(predicted_edge) / max(1.0, self.TREND_ENTRY_THRESHOLD), 0.0, 1.0)

        buy_quote = math.floor(center - quote_edge)
        sell_quote = math.ceil(center + quote_edge)

        position_gap = self.projected_position() - target_position
        if position_gap > max(3, self.soft_limit // 4):
            buy_quote -= 1
            sell_quote -= 1
        elif position_gap < -max(3, self.soft_limit // 4):
            buy_quote += 1
            sell_quote += 1

        if state_name == "trend_up" and self.projected_position() <= target_position:
            sell_quote = None
        elif state_name == "trend_down" and self.projected_position() >= target_position:
            buy_quote = None
        elif state_name == "volatile" and abs(self.projected_position()) <= 6:
            buy_quote = None
            sell_quote = None
        return self.clamp_inside_spread(buy_quote, sell_quote)

    def passive_size(self, side: str, state_name: str) -> int:
        size = self.PASSIVE_SIZE
        if state_name == "volatile":
            size = max(1, size - 3)
        elif state_name in {"trend_up", "trend_down"}:
            size = max(1, size + 1)

        position = self.projected_position()
        if side == "BUY":
            if position <= -20:
                size += 1
            elif position >= 20:
                size = max(1, size - 2)
        else:
            if position >= 20:
                size += 1
            elif position <= -20:
                size = max(1, size - 2)

        size = int(round(size * max(0.45, 1.0 - (self.SIZE_INVENTORY_PRESSURE * self.inventory_pressure(side)))))
        if self.adverse_ewma > 0.45:
            size = max(1, size - 2)
        return size

    def allow_passive(self, side: str, state_name: str) -> bool:
        position = self.projected_position()
        if side == "BUY" and position >= self.soft_limit:
            return False
        if side == "SELL" and position <= -self.soft_limit:
            return False
        if state_name in {"volatile", "flatten"} and abs(position) <= 6:
            return False
        if self.adverse_ewma > 0.75 and self.inventory_pressure(side) > 0.65:
            return False
        return True

    def sweep_side(
        self,
        side: str,
        state_name: str,
        target_position: int,
        reservation_price: float,
        predicted_edge: float,
        volatility: float,
    ) -> bool:
        traded = False
        levels = self.sell_levels[:3] if side == "BUY" else self.buy_levels[:3]
        threshold = self.take_edge(side, state_name, predicted_edge, volatility)
        for price, volume in levels:
            projected = self.projected_position()
            edge = reservation_price - float(price) if side == "BUY" else float(price) - reservation_price
            if edge < threshold:
                break

            if side == "BUY":
                desired = max(0, target_position - projected)
                if state_name == "trend_down" and desired <= 0:
                    continue
                take_limit = int(self.MAX_TAKE_SIZE)
                if state_name == "trend_up":
                    take_limit += 2
                take_limit = max(1, int(round(take_limit * max(0.55, 1.0 - 0.30 * self.inventory_pressure("BUY")))))
                quantity = min(int(volume), self.buy_capacity, take_limit)
                if desired > 0:
                    quantity = min(quantity, max(1, desired))
                else:
                    quantity = min(quantity, 3 if state_name == "range" else 2)
                if quantity <= 0:
                    continue
                self.add_buy(int(price), quantity)
                traded = True
            else:
                desired = max(0, projected - target_position)
                if state_name == "trend_up" and desired <= 0:
                    continue
                take_limit = int(self.MAX_TAKE_SIZE)
                if state_name == "trend_down":
                    take_limit += 2
                take_limit = max(1, int(round(take_limit * max(0.55, 1.0 - 0.30 * self.inventory_pressure("SELL")))))
                quantity = min(int(volume), self.sell_capacity, take_limit)
                if desired > 0:
                    quantity = min(quantity, max(1, desired))
                else:
                    quantity = min(quantity, 3 if state_name == "range" else 2)
                if quantity <= 0:
                    continue
                self.add_sell(int(price), quantity)
                traded = True
        return traded

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        self.update_fill_feedback()
        predicted_now, predicted_next, fit_quality, volatility = self.regression_metrics()
        _hybrid_fair, hybrid_alpha = self.hybrid_alpha()
        regression_edge = (predicted_next - float(self.mid)) * self.ALPHA_EDGE_SCALE
        predicted_edge = (
            (1.0 - self.ALPHA_BLEND_WEIGHT) * regression_edge
            + self.ALPHA_BLEND_WEIGHT * hybrid_alpha
        )
        raw_trend = (
            predicted_edge
            + 0.20 * self.imbalance * max(1.0, float(self.spread) / 2.0)
            + 0.08 * self.momentum
        ) / max(1.0, volatility)
        raw_toxic = (
            max(0.0, (float(self.spread) - self.TOXIC_SPREAD_THRESHOLD) / 4.0)
            + max(0.0, volatility - self.TOXIC_VOL_THRESHOLD)
            + 0.45 * max(0.0, abs(self.imbalance) - 0.20)
            + 0.35 * self.adverse_ewma
        )
        self.trend_score = self.smooth_score(self.trend_score, raw_trend)
        self.toxic_score = max(0.0, self.smooth_score(self.toxic_score, raw_toxic))

        state_name = self.classify_state(fit_quality)
        hybrid_alpha = self.guarded_hybrid_alpha(hybrid_alpha, regression_edge, state_name)
        predicted_next = float(self.mid) + predicted_edge
        target_position = self.target_position(state_name, predicted_edge)
        reservation_price = self.fair_value(
            state_name,
            target_position,
            predicted_now,
            predicted_next,
            hybrid_alpha,
            volatility,
        )
        took_buy = self.sweep_side("BUY", state_name, target_position, reservation_price, predicted_edge, volatility)
        took_sell = self.sweep_side("SELL", state_name, target_position, reservation_price, predicted_edge, volatility)

        buy_quote, sell_quote = self.passive_quotes(
            reservation_price,
            state_name,
            target_position,
            predicted_edge,
            volatility,
        )
        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.allow_passive("BUY", state_name)
        ):
            if state_name == "range" or position < target_position:
                quantity = min(self.passive_size("BUY", state_name), self.buy_capacity)
                if state_name != "range":
                    quantity = min(quantity, max(1, target_position - position))
                self.add_buy(buy_quote, quantity)

        position = self.projected_position()
        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.allow_passive("SELL", state_name)
        ):
            if state_name == "range" or position > target_position:
                quantity = min(self.passive_size("SELL", state_name), self.sell_capacity)
                if state_name != "range":
                    quantity = min(quantity, max(1, position - target_position))
                self.add_sell(sell_quote, quantity)

        self.memory = {
            "fill_quality_ewma": round(self.fill_quality_ewma, 4),
            "adverse_ewma": round(self.adverse_ewma, 4),
            "trend_score": round(self.trend_score, 4),
            "toxic_score": round(self.toxic_score, 4),
            "pending_fills": [
                {
                    "timestamp": round(fill["timestamp"], 1),
                    "price": round(fill["price"], 1),
                    "side": round(fill["side"], 1),
                    "qty": round(fill["qty"], 1),
                }
                for fill in self.pending_fills[-8:]
            ],
            "seen_trade_keys": self.seen_trade_keys[-24:],
        }
        return self.orders


class Trader:
    POSITION_LIMITS: Dict[str, int] = {
        "EMERALDS": 80,
        "TOMATOES": 80,
    }

    PRODUCT_TRADERS = {
        "EMERALDS": EmeraldsTrader,
        "TOMATOES": TomatoesTrader,
    }

    def load_trader_data(self, trader_data: str) -> Tuple[Dict[str, List[float]], Dict[str, Dict[str, object]]]:
        if not trader_data:
            return {}, {}
        try:
            parsed = json.loads(trader_data)
        except json.JSONDecodeError:
            return {}, {}

        raw_history = parsed.get("mid_history", {})
        cleaned: Dict[str, List[float]] = {}
        if isinstance(raw_history, dict):
            for product, values in raw_history.items():
                if isinstance(values, list):
                    cleaned[product] = [float(value) for value in values[-BaseProductTrader.HISTORY_LENGTH :]]

        raw_memory = parsed.get("memory", {})
        memory: Dict[str, Dict[str, object]] = {}
        if isinstance(raw_memory, dict):
            for product, values in raw_memory.items():
                if isinstance(values, dict):
                    memory[product] = values
        return cleaned, memory

    def build_trader_data(self, mid_history: Dict[str, List[float]], memory: Dict[str, Dict[str, object]]) -> str:
        return json.dumps({"mid_history": mid_history, "memory": memory}, separators=(",", ":"))

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        mid_history, memory = self.load_trader_data(state.traderData)
        next_memory: Dict[str, Dict[str, object]] = dict(memory)

        for product in state.order_depths:
            if product not in self.PRODUCT_TRADERS:
                result[product] = []
                continue

            trader_class = self.PRODUCT_TRADERS[product]
            trader = trader_class(
                product,
                state,
                mid_history,
                self.POSITION_LIMITS[product],
                memory.get(product, {}),
            )
            result[product] = trader.run()
            exported_memory = trader.export_memory()
            if exported_memory:
                next_memory[product] = exported_memory

        conversions = 0
        trader_data = self.build_trader_data(mid_history, next_memory)
        return result, conversions, trader_data
