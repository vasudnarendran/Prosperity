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
    "REGRESSION_WINDOW": 8,
    "REGRESSION_HORIZON": 0.5,
    "REFERENCE_WEIGHT": 0.44,
    "MICRO_WEIGHT": 0.30,
    "FLOW_WEIGHT": 0.10,
    "REGRESSION_EDGE_SCALE": 1.18,
    "ALPHA_CAP": 2.2,
    "TREND_THRESHOLD": 1.18,
    "TOXIC_SPREAD_THRESHOLD": 15.0,
    "TOXIC_VOL_THRESHOLD": 3.2,
    "REGIME_SMOOTH_ALPHA": 0.28,
    "INVENTORY_SKEW": 0.005,
    "SOFT_LIMIT_RATIO": 0.57,
    "TARGET_TREND_SIZE": 0.52,
    "TARGET_RANGE_SIZE": 0.12,
    "TARGET_STRETCH_DAMP": 0.22,
    "BASE_QUOTE_EDGE": 3.0,
    "QUOTE_VOL_COEF": 0.18,
    "QUOTE_INV_COEF": 0.80,
    "QUOTE_TOXIC_BONUS": 1.30,
    "QUOTE_TREND_SKEW": 0.55,
    "BASE_TAKE_EDGE": 0.95,
    "TAKE_TREND_REWARD": 0.32,
    "TAKE_TOXIC_PENALTY": 0.42,
    "TAKE_STRETCH_PENALTY": 0.22,
    "PASSIVE_SIZE": 7,
    "MAX_TAKE_SIZE": 10,
    "MARKOUT_DELAY_TICKS": 400,
    "FEEDBACK_EWMA_ALPHA": 0.18,
    "GOOD_FILL_BONUS": 0.06,
    "BAD_FILL_PENALTY": 0.22,
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

    def normalized_stretch(self, reference_price: float, volatility: float) -> float:
        return (float(self.mid) - reference_price) / max(1.0, volatility)

    def market_speed(self, volatility: float) -> float:
        vol_component = clip((volatility - 1.0) / 2.5, 0.0, 1.0)
        imb_component = clip((abs(self.imbalance) - 0.08) / 0.45, 0.0, 1.0)
        return clip(0.55 * vol_component + 0.45 * imb_component, 0.0, 1.0)

    def smooth_score(self, previous: float, current: float) -> float:
        alpha = self.REGIME_SMOOTH_ALPHA
        if previous * current < 0:
            alpha = max(0.12, alpha - 0.10)
        return (1.0 - alpha) * previous + alpha * current

    def hybrid_alpha(self, reference_price: float, regression_edge: float, volatility: float) -> float:
        speed = self.market_speed(volatility)
        ref_weight = self.REFERENCE_WEIGHT * (1.0 - 0.20 * speed)
        micro_weight = self.MICRO_WEIGHT * (1.0 + 0.35 * speed)
        flow_weight = self.FLOW_WEIGHT * (1.0 + 0.50 * speed)
        total = ref_weight + micro_weight + flow_weight
        mid_weight = max(0.10, 1.0 - total)
        weight_sum = ref_weight + micro_weight + flow_weight + mid_weight
        ref_weight /= weight_sum
        micro_weight /= weight_sum
        flow_weight /= weight_sum
        mid_weight /= weight_sum

        half_spread = max(1.0, float(self.spread) / 2.0)
        flow_signal = (self.imbalance * half_spread) + (0.35 * regression_edge) + (0.15 * self.momentum)
        fair = (
            ref_weight * reference_price
            + mid_weight * float(self.mid)
            + micro_weight * float(self.micro)
            + flow_weight * (float(self.mid) + flow_signal)
        )
        return clip(fair - float(self.mid), -self.ALPHA_CAP, self.ALPHA_CAP)

    def guarded_alpha(
        self,
        alpha: float,
        regression_edge: float,
        reference_price: float,
        volatility: float,
        state: str,
    ) -> float:
        weight = 1.0
        if state == "range":
            weight *= 0.60
        if alpha * regression_edge < 0:
            weight *= 0.55
        if alpha * self.imbalance < 0:
            weight *= 0.70
        if alpha * self.momentum < 0:
            weight *= 0.80

        stretch = self.normalized_stretch(reference_price, volatility)
        if alpha * stretch > 0:
            weight *= max(0.45, 1.0 - 0.15 * max(0.0, abs(stretch) - 1.0))

        position = self.projected_position()
        if alpha * position > 0:
            weight *= max(0.30, 1.0 - 0.45 * self.inventory_pressure())

        return alpha * weight

    def classify_state(self, trend_score: float, toxic_score: float, fit_quality: float) -> str:
        if toxic_score >= 0.95:
            return "volatile"
        if (
            trend_score >= self.TREND_THRESHOLD
            and fit_quality >= 0.42
            and self.imbalance > 0.02
            and float(self.micro) >= float(self.mid)
        ):
            return "trend_up"
        if (
            trend_score <= -self.TREND_THRESHOLD
            and fit_quality >= 0.42
            and self.imbalance < -0.02
            and float(self.micro) <= float(self.mid)
        ):
            return "trend_down"
        return "range"

    def target_position(self, state_name: str, trend_score: float, stretch: float) -> int:
        if state_name == "volatile":
            return 0

        if state_name == "trend_up":
            conviction = clip(abs(trend_score) / (1.65 * self.TREND_THRESHOLD), 0.0, 1.0)
            base = self.soft_limit * self.TARGET_TREND_SIZE * conviction
            damp = max(0.45, 1.0 - self.TARGET_STRETCH_DAMP * max(0.0, stretch - 0.8))
            return min(self.soft_limit, int(round(base * damp)))

        if state_name == "trend_down":
            conviction = clip(abs(trend_score) / (1.65 * self.TREND_THRESHOLD), 0.0, 1.0)
            base = self.soft_limit * self.TARGET_TREND_SIZE * conviction
            damp = max(0.45, 1.0 - self.TARGET_STRETCH_DAMP * max(0.0, -stretch - 0.8))
            return max(-self.soft_limit, -int(round(base * damp)))

        range_target = -self.soft_limit * self.TARGET_RANGE_SIZE * clip(stretch / 1.5, -1.0, 1.0)
        return int(round(range_target))

    def fair_value(self, regression_edge: float, alpha: float, target_position: int, state_name: str, stretch: float) -> float:
        inventory_gap = self.projected_position() - target_position
        fair = float(self.mid) + alpha + (self.REGRESSION_EDGE_SCALE * regression_edge)
        fair -= inventory_gap * self.INVENTORY_SKEW * (1.0 + 0.6 * self.toxic_score)
        if state_name == "range":
            fair -= 0.10 * stretch
        return fair

    def take_edge(self, side: str, state_name: str, trend_score: float, stretch: float) -> float:
        edge = self.BASE_TAKE_EDGE
        edge += self.TAKE_TOXIC_PENALTY * self.toxic_score
        edge += max(0.0, self.adverse_ewma - 0.35) * self.BAD_FILL_PENALTY
        edge -= max(0.0, self.fill_quality_ewma) * self.GOOD_FILL_BONUS
        if state_name == "range":
            edge += 0.08

        if side == "BUY" and state_name == "trend_up":
            edge -= self.TAKE_TREND_REWARD * clip(abs(trend_score) / (1.8 * self.TREND_THRESHOLD), 0.0, 1.0)
        elif side == "SELL" and state_name == "trend_down":
            edge -= self.TAKE_TREND_REWARD * clip(abs(trend_score) / (1.8 * self.TREND_THRESHOLD), 0.0, 1.0)
        elif state_name in {"trend_up", "trend_down"}:
            edge += 0.22

        if side == "BUY" and stretch > 1.0:
            edge += self.TAKE_STRETCH_PENALTY * min(1.2, stretch - 1.0)
        elif side == "SELL" and stretch < -1.0:
            edge += self.TAKE_STRETCH_PENALTY * min(1.2, abs(stretch) - 1.0)

        edge += 0.18 * self.inventory_pressure(side)
        return max(0.45, edge)

    def quote_edge(self, volatility: float) -> float:
        edge = self.BASE_QUOTE_EDGE
        edge += self.QUOTE_VOL_COEF * min(3.0, volatility)
        edge += self.QUOTE_INV_COEF * self.inventory_pressure()
        edge += self.QUOTE_TOXIC_BONUS * self.toxic_score
        edge += max(0.0, self.adverse_ewma - 0.30) * self.BAD_FILL_PENALTY
        edge -= max(0.0, self.fill_quality_ewma) * self.GOOD_FILL_BONUS
        if self.toxic_score < 0.25 and self.inventory_pressure() < 0.25:
            edge -= 0.12
        return clip(edge, 1.2, 8.0)

    def passive_quotes(
        self,
        fair: float,
        state_name: str,
        trend_score: float,
        target_position: int,
        volatility: float,
    ) -> Tuple[Optional[int], Optional[int]]:
        center = fair
        if state_name == "trend_up":
            center += self.QUOTE_TREND_SKEW * clip(abs(trend_score) / (2.0 * self.TREND_THRESHOLD), 0.0, 1.0)
        elif state_name == "trend_down":
            center -= self.QUOTE_TREND_SKEW * clip(abs(trend_score) / (2.0 * self.TREND_THRESHOLD), 0.0, 1.0)

        edge = self.quote_edge(volatility)
        buy_quote = math.floor(center - edge)
        sell_quote = math.ceil(center + edge)

        position_gap = self.projected_position() - target_position
        if position_gap > max(3, self.soft_limit // 4):
            buy_quote -= 1
            sell_quote -= 1
        elif position_gap < -max(3, self.soft_limit // 4):
            buy_quote += 1
            sell_quote += 1

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def passive_size(self, side: str, state_name: str, target_position: int) -> int:
        size = int(self.PASSIVE_SIZE)
        if state_name == "volatile":
            size = max(1, size - 3)
        elif state_name in {"trend_up", "trend_down"}:
            size += 1

        size -= int(round(2.0 * self.toxic_score))
        size -= int(round(2.0 * max(0.0, self.adverse_ewma - 0.40)))

        position_gap = self.projected_position() - target_position
        if side == "BUY":
            if position_gap < 0:
                size += 1
            elif position_gap > 0:
                size -= 2
        else:
            if position_gap > 0:
                size += 1
            elif position_gap < 0:
                size -= 2

        size = int(round(size * max(0.50, 1.0 - 0.35 * self.inventory_pressure(side))))
        return max(1, min(12, size))

    def allow_passive(self, side: str, state_name: str, target_position: int, stretch: float) -> bool:
        position = self.projected_position()
        if side == "BUY" and position >= self.soft_limit:
            return False
        if side == "SELL" and position <= -self.soft_limit:
            return False
        if self.toxic_score >= 1.05 and abs(position) <= 4:
            return False
        if self.adverse_ewma > 0.75 and self.inventory_pressure(side) > 0.50:
            return False

        if side == "BUY" and state_name == "trend_down" and position >= target_position:
            return False
        if side == "SELL" and state_name == "trend_up" and position <= target_position:
            return False

        if side == "BUY" and stretch > 1.5 and state_name != "trend_up":
            return False
        if side == "SELL" and stretch < -1.5 and state_name != "trend_down":
            return False

        return True

    def sweep_side(
        self,
        side: str,
        fair: float,
        state_name: str,
        trend_score: float,
        stretch: float,
        target_position: int,
    ) -> bool:
        traded = False
        levels = self.sell_levels[:3] if side == "BUY" else self.buy_levels[:3]
        threshold = self.take_edge(side, state_name, trend_score, stretch)
        for price, volume in levels:
            projected = self.projected_position()
            edge = fair - float(price) if side == "BUY" else float(price) - fair
            if edge < threshold:
                break

            if side == "BUY":
                desired = max(0, target_position - projected)
                take_limit = int(self.MAX_TAKE_SIZE)
                if state_name == "trend_up" and trend_score > 1.25 * self.TREND_THRESHOLD and self.toxic_score < 0.45:
                    take_limit += 2
                take_limit = max(1, int(round(take_limit * max(0.55, 1.0 - 0.25 * self.inventory_pressure("BUY")))))
                quantity = min(int(volume), self.buy_capacity, take_limit)
                if desired > 0:
                    quantity = min(quantity, max(1, desired))
                elif state_name != "range" and edge < threshold + 0.35:
                    continue
                else:
                    if edge < threshold + 0.55:
                        continue
                    quantity = min(quantity, 2)
                if quantity <= 0:
                    continue
                self.add_buy(int(price), quantity)
                traded = True
            else:
                desired = max(0, projected - target_position)
                take_limit = int(self.MAX_TAKE_SIZE)
                if state_name == "trend_down" and trend_score < -1.25 * self.TREND_THRESHOLD and self.toxic_score < 0.45:
                    take_limit += 2
                take_limit = max(1, int(round(take_limit * max(0.55, 1.0 - 0.25 * self.inventory_pressure("SELL")))))
                quantity = min(int(volume), self.sell_capacity, take_limit)
                if desired > 0:
                    quantity = min(quantity, max(1, desired))
                elif state_name != "range" and edge < threshold + 0.35:
                    continue
                else:
                    if edge < threshold + 0.55:
                        continue
                    quantity = min(quantity, 2)
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
        reference_price = 0.55 * float(self.recent_average) + 0.45 * predicted_now
        regression_edge = predicted_next - float(self.mid)
        raw_alpha = self.hybrid_alpha(reference_price, regression_edge, volatility)

        raw_trend = (
            0.75 * regression_edge
            + 0.45 * raw_alpha
            + 0.18 * self.imbalance * max(1.0, float(self.spread) / 2.0)
            + 0.12 * self.momentum
        ) * (0.45 + 0.55 * fit_quality) / max(1.0, volatility)
        raw_toxic = (
            max(0.0, (float(self.spread) - self.TOXIC_SPREAD_THRESHOLD) / 4.0)
            + max(0.0, volatility - self.TOXIC_VOL_THRESHOLD)
            + 0.55 * max(0.0, abs(self.imbalance) - 0.25)
            + 0.45 * self.adverse_ewma
        )

        self.trend_score = self.smooth_score(self.trend_score, raw_trend)
        self.toxic_score = max(0.0, self.smooth_score(self.toxic_score, raw_toxic))
        state_name = self.classify_state(self.trend_score, self.toxic_score, fit_quality)

        alpha = self.guarded_alpha(raw_alpha, regression_edge, reference_price, volatility, state_name)
        stretch = self.normalized_stretch(reference_price, volatility)
        target_position = self.target_position(state_name, self.trend_score, stretch)
        fair = self.fair_value(regression_edge, alpha, target_position, state_name, stretch)

        took_buy = self.sweep_side("BUY", fair, state_name, self.trend_score, stretch, target_position)
        took_sell = self.sweep_side("SELL", fair, state_name, self.trend_score, stretch, target_position)

        fair = self.fair_value(regression_edge, alpha, target_position, state_name, stretch)
        buy_quote, sell_quote = self.passive_quotes(fair, state_name, self.trend_score, target_position, volatility)

        position = self.projected_position()
        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.allow_passive("BUY", state_name, target_position, stretch)
        ):
            if state_name == "range" or position < target_position:
                quantity = min(self.passive_size("BUY", state_name, target_position), self.buy_capacity)
                if state_name != "range":
                    quantity = min(quantity, max(1, target_position - position))
                self.add_buy(buy_quote, quantity)

        position = self.projected_position()
        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.allow_passive("SELL", state_name, target_position, stretch)
        ):
            if state_name == "range" or position > target_position:
                quantity = min(self.passive_size("SELL", state_name, target_position), self.sell_capacity)
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
