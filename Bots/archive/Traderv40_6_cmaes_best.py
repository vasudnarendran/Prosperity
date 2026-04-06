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
    "RESIDUAL_REVERT_WEIGHT": 0.12,
    "IMBALANCE_WEIGHT": 0.35,
    "INVENTORY_SKEW": 0.005,
    "BASE_TAKE_EDGE": 0.7516267301,
    "BASE_QUOTE_EDGE": 2.6470054123,
    "MAX_QUOTE_EDGE": 9.0,
    "PASSIVE_SIZE": 8,
    "MAX_TAKE_SIZE": 10,
    "REGRESSION_WINDOW": 8,
    "REGRESSION_HORIZON": 0.5,
    "TREND_EDGE_THRESHOLD": 1.00,
    "STRONG_TREND_EDGE": 2.50,
    "FIT_THRESHOLD": 0.45,
    "TREND_IMBALANCE_THRESHOLD": 0.12,
    "TOXIC_SPREAD_THRESHOLD": 15.0,
    "TOXIC_VOLATILITY_THRESHOLD": 3.2,
    "SOFT_LIMIT_RATIO": 0.5489928521,
    "POSITION_BIAS_DIVISOR": 12.0,
    "TREND_FAIR_BONUS": 0.25,
    "TREND_ENTRY_TAKE_BONUS": 3.0,
    "TREND_HOLD_EXIT_BONUS": 0.55,
    "STRONG_TREND_HOLD_EXIT_BONUS": 0.90,
    "TREND_PASSIVE_PUSH": 0.0,
    "TREND_PASSIVE_SIZE_BONUS": 2.0,
    "VOL_CONTROL_WINDOW": 8,
    "TIME_HORIZON_TICKS": 10000.0,
    "GAMMA_RANGE": 0.69283327,
    "GAMMA_TREND": 0.10,
    "GAMMA_VOLATILE": 0.40,
    "RESERVATION_SCALE": 0.02,
    "SPREAD_VOL_COEF": 0.1,
    "SPREAD_INV_COEF": 1.1081637,
    "SPREAD_TIME_COEF": 1.7791177,
    "TREND_RESERVATION_BIAS": 0.04,
    "RANGE_RESERVATION_BIAS": 0.26486122,
    "ALPHA_EDGE_SCALE": 1.3634015054,
    "ALPHA_IMBALANCE_SCALE": 0.7,
    "ALPHA_THRESHOLD_SCALE": 1.03,
    "TREND_SELL_HOLD_EXTRA": 0.24,
    "TREND_BUY_TAKE_EXTRA": 0.08,
    "TREND_QUOTE_LIFT_EXTRA": 1.0,
    "HOLD_TIME_COEF": 0.08,
    "HOLD_VOL_COEF": 0.0,
    "ALPHA_REFERENCE_WEIGHT": 0.45,
    "ALPHA_MID_WEIGHT": 0.20,
    "ALPHA_MICRO_WEIGHT": 0.25,
    "ALPHA_FLOW_WEIGHT": 0.10,
    "ALPHA_FLOW_SPREAD_SCALE": 0.50,
    "ALPHA_BLEND_WEIGHT": 0.2658438089,
    "FAIR_ALPHA_WEIGHT": 0.420735319,
    "ALPHA_CAP": 2.20,
    "RANGE_ALPHA_DAMP": 0.3583177833,
    "CONFLICT_ALPHA_DAMP": 0.4798002143,
    "MOMENTUM_ALPHA_DAMP": 0.7,
    "POSITION_ALPHA_DAMP_START": 15.3003931233,
    "POSITION_ALPHA_DAMP_END": 26.7466168674,
    "CALM_SPREAD_THRESHOLD": 12.0,
    "CALM_VOL_THRESHOLD": 1.8,
    "CALM_IMBALANCE_THRESHOLD": 0.20,
    "FAST_VOL_THRESHOLD": 2.4,
    "FAST_IMBALANCE_THRESHOLD": 0.32,
    "FAST_MICRO_BONUS": 0.06,
    "FAST_IMBALANCE_BONUS": 0.14,
    "FAST_ALPHA_BONUS": 0.08,
    "FAST_TAKE_EDGE_BONUS": 0.12,
    "FAST_TAKE_SIZE_BONUS": 2.0,
    "FAST_TARGET_BONUS": 4.0,
    "CALM_JOIN_IMPROVEMENT": 1.0,
    "CALM_QUOTE_EDGE_MULT": 0.94,
    "FAST_QUOTE_EDGE_MULT": 1.02,
    "INVENTORY_EDGE_PRESSURE": 0.42,
    "INVENTORY_SIZE_PRESSURE": 0.35,
    "MARKOUT_DELAY_TICKS": 400,
    "FEEDBACK_EWMA_ALPHA": 0.18,
    "GOOD_FILL_TAKE_BONUS": 0.04,
    "BAD_FILL_TAKE_PENALTY": 0.20,
    "BAD_FILL_QUOTE_PENALTY": 0.06,
    "REGIME_EWMA_ALPHA": 0.2402714583,
    "LEAN_SCORE": 0.445547723,
    "STRONG_SCORE": 1.0628205438,
    "DEFENSIVE_VOL_THRESHOLD": 3.3735488393,
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
        self.prev_mid = float(self.memory.get("prev_mid", self.mid or 0.0))
        self.ewma_mid = float(self.memory.get("ewma_mid", self.mid or 0.0))
        self.ewma_return = float(self.memory.get("ewma_return", 0.0))
        self.ewma_abs_return = float(self.memory.get("ewma_abs_return", 0.0))
        self.ewma_micro_gap = float(self.memory.get("ewma_micro_gap", 0.0))
        self.ewma_imbalance = float(self.memory.get("ewma_imbalance", 0.0))
        self.regime_score = float(self.memory.get("regime_score", 0.0))
        self.mode = str(self.memory.get("mode", "neutral"))
        self.fill_quality_ewma = float(self.memory.get("fill_quality_ewma", 0.0))
        self.adverse_ewma = float(self.memory.get("adverse_ewma", 0.0))
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

    def update_state(self) -> None:
        alpha = self.REGIME_EWMA_ALPHA
        mid = float(self.mid)
        micro_gap = float(self.micro) - mid
        ret = mid - self.prev_mid

        self.ewma_mid = (1.0 - alpha) * self.ewma_mid + alpha * mid
        self.ewma_return = (1.0 - alpha) * self.ewma_return + alpha * ret
        self.ewma_abs_return = (1.0 - alpha) * self.ewma_abs_return + alpha * abs(ret)
        self.ewma_micro_gap = (1.0 - alpha) * self.ewma_micro_gap + alpha * micro_gap
        self.ewma_imbalance = (1.0 - alpha) * self.ewma_imbalance + alpha * self.imbalance
        self.prev_mid = mid

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

    def alpha_score(self, predicted_edge: float) -> float:
        scale = max(0.6, self.ewma_abs_return, abs(predicted_edge))
        raw = (
            0.70 * (predicted_edge / scale)
            + 0.20 * (self.ewma_micro_gap / scale)
            + 0.10 * self.ewma_imbalance
        )
        self.regime_score = 0.75 * self.regime_score + 0.25 * raw
        return clip(self.regime_score, -3.0, 3.0)

    def classify_mode(self, score: float) -> str:
        prev = self.mode
        if self.adverse_ewma > 0.70:
            return "defensive"
        if self.ewma_abs_return >= self.DEFENSIVE_VOL_THRESHOLD and abs(score) < self.LEAN_SCORE:
            return "defensive"

        enter_lean = self.LEAN_SCORE
        exit_lean = self.LEAN_SCORE * 0.65
        enter_strong = self.STRONG_SCORE
        exit_strong = self.STRONG_SCORE * 0.75

        if prev == "strong_up" and score >= exit_strong:
            return "strong_up"
        if prev == "lean_up" and score >= exit_lean:
            return "lean_up"
        if prev == "strong_down" and score <= -exit_strong:
            return "strong_down"
        if prev == "lean_down" and score <= -exit_lean:
            return "lean_down"

        if score >= enter_strong:
            return "strong_up"
        if score >= enter_lean:
            return "lean_up"
        if score <= -enter_strong:
            return "strong_down"
        if score <= -enter_lean:
            return "lean_down"
        return "neutral"

    def market_style(
        self,
        regime: str,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
    ) -> Dict[str, float]:
        calm = (
            regime == "range"
            and float(self.spread) <= self.CALM_SPREAD_THRESHOLD
            and volatility <= self.CALM_VOL_THRESHOLD
            and abs(self.imbalance) <= self.CALM_IMBALANCE_THRESHOLD
        )
        fast = (
            regime in {"trend_up", "trend_down"}
            or volatility >= self.FAST_VOL_THRESHOLD
            or abs(self.imbalance) >= self.FAST_IMBALANCE_THRESHOLD
        )
        style = {
            "micro_bonus": 0.0,
            "imbalance_bonus": 0.0,
            "alpha_bonus": 0.0,
            "quote_mult": 1.0,
            "join_ticks": 0.0,
            "take_edge_shift": 0.0,
            "take_size_bonus": 0.0,
            "target_bonus": 0.0,
        }
        if calm:
            style["quote_mult"] *= self.CALM_QUOTE_EDGE_MULT
            if abs(self.projected_position()) <= max(6, int(0.25 * self.soft_limit)) and self.adverse_ewma < 0.45:
                style["join_ticks"] = self.CALM_JOIN_IMPROVEMENT
        elif fast:
            style["micro_bonus"] = self.FAST_MICRO_BONUS
            style["imbalance_bonus"] = self.FAST_IMBALANCE_BONUS
            style["alpha_bonus"] = self.FAST_ALPHA_BONUS
            style["quote_mult"] *= self.FAST_QUOTE_EDGE_MULT
            if fit_quality >= self.FIT_THRESHOLD and abs(self.imbalance) >= self.TREND_IMBALANCE_THRESHOLD:
                style["take_edge_shift"] -= self.FAST_TAKE_EDGE_BONUS
                style["take_size_bonus"] += self.FAST_TAKE_SIZE_BONUS
                if self.inventory_pressure() <= 0.65:
                    style["target_bonus"] += self.FAST_TARGET_BONUS

        if self.fill_quality_ewma > 0.25 and self.adverse_ewma < 0.35:
            style["take_edge_shift"] -= self.GOOD_FILL_TAKE_BONUS
            style["quote_mult"] *= 0.97
            style["take_size_bonus"] += 1.0
        if self.adverse_ewma > 0.35:
            style["take_edge_shift"] += self.BAD_FILL_TAKE_PENALTY * self.adverse_ewma
            style["quote_mult"] *= 1.0 + (self.BAD_FILL_QUOTE_PENALTY * self.adverse_ewma)

        return style

    def hybrid_alpha(self, style: Dict[str, float]) -> Tuple[float, float]:
        reference_price = float(self.recent_average)
        half_spread = max(1.0, float(self.spread) / 2.0)
        flow_signal = self.imbalance * half_spread * self.ALPHA_FLOW_SPREAD_SCALE
        micro_weight = self.ALPHA_MICRO_WEIGHT + style["micro_bonus"]
        flow_weight = self.ALPHA_FLOW_WEIGHT + style["alpha_bonus"]
        hybrid_fair = (
            self.ALPHA_REFERENCE_WEIGHT * reference_price
            + self.ALPHA_MID_WEIGHT * float(self.mid)
            + micro_weight * float(self.micro)
            + flow_weight * (float(self.mid) + flow_signal)
        )
        alpha = hybrid_fair - float(self.mid)
        alpha = max(-self.ALPHA_CAP, min(self.ALPHA_CAP, alpha))
        return hybrid_fair, alpha

    def guarded_hybrid_alpha(self, hybrid_alpha: float, regression_edge: float, regime: str) -> float:
        weight = 1.0
        if regime == "range":
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

    def control_gamma(self, regime: str) -> float:
        if regime == "trend_up" or regime == "trend_down":
            return self.GAMMA_TREND
        if regime == "volatile":
            return self.GAMMA_VOLATILE
        return self.GAMMA_RANGE

    def reservation_adjustment(
        self,
        regime: str,
        target_position: int,
        predicted_edge: float,
        volatility: float,
    ) -> float:
        position = self.projected_position()
        inventory_gap = position - target_position
        gamma = self.control_gamma(regime)
        tau = self.time_fraction_remaining()
        reservation_shift = inventory_gap * gamma * max(0.6, volatility) * self.RESERVATION_SCALE * max(0.35, tau)

        if regime == "trend_up":
            reservation_shift -= self.TREND_RESERVATION_BIAS * max(0.0, predicted_edge)
        elif regime == "trend_down":
            reservation_shift += self.TREND_RESERVATION_BIAS * max(0.0, -predicted_edge)
        elif regime == "range":
            if predicted_edge > 0:
                reservation_shift -= self.RANGE_RESERVATION_BIAS * predicted_edge
            else:
                reservation_shift += self.RANGE_RESERVATION_BIAS * abs(predicted_edge)

        return reservation_shift

    def classify_state(
        self,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
    ) -> str:
        trend_threshold = self.TREND_EDGE_THRESHOLD * self.ALPHA_THRESHOLD_SCALE
        if float(self.spread) >= self.TOXIC_SPREAD_THRESHOLD and volatility >= self.TOXIC_VOLATILITY_THRESHOLD:
            return "volatile"
        if (
            predicted_edge >= trend_threshold
            and fit_quality >= self.FIT_THRESHOLD
            and self.imbalance >= self.TREND_IMBALANCE_THRESHOLD
            and self.momentum >= 0.75
            and float(self.micro) >= float(self.mid)
        ):
            return "trend_up"
        if (
            predicted_edge <= -trend_threshold
            and fit_quality >= self.FIT_THRESHOLD
            and self.imbalance <= -self.TREND_IMBALANCE_THRESHOLD
            and self.momentum <= -0.75
            and float(self.micro) <= float(self.mid)
        ):
            return "trend_down"
        return "range"

    def target_band(self, regime: str, predicted_edge: float, fit_quality: float) -> Tuple[int, int]:
        conviction = abs(predicted_edge) * max(0.5, fit_quality)
        if regime == "trend_up":
            return (22, 44) if conviction >= self.STRONG_TREND_EDGE else (10, 28)
        if regime == "trend_down":
            return (-44, -22) if conviction >= self.STRONG_TREND_EDGE else (-28, -10)
        if regime == "volatile":
            return -6, 6
        return -14, 14

    def target_position(
        self,
        regime: str,
        predicted_edge: float,
        fit_quality: float,
        style: Dict[str, float],
        mode: str,
    ) -> int:
        lower, upper = self.target_band(regime, predicted_edge, fit_quality)
        if mode == "defensive":
            return 0
        if mode == "lean_up":
            lower = max(lower, 8)
            upper = min(self.soft_limit, upper + 2)
        elif mode == "strong_up":
            lower = max(lower, 18)
            upper = min(self.soft_limit, upper + 4)
        elif mode == "lean_down":
            upper = min(upper, -8)
            lower = max(-self.soft_limit, lower - 2)
        elif mode == "strong_down":
            upper = min(upper, -18)
            lower = max(-self.soft_limit, lower - 4)
        if regime == "trend_up":
            upper = min(self.soft_limit, upper + int(style["target_bonus"]))
        elif regime == "trend_down":
            lower = max(-self.soft_limit, lower - int(style["target_bonus"]))
        position = self.projected_position()
        if position < lower:
            return lower
        if position > upper:
            return upper
        if regime == "trend_up":
            return upper
        if regime == "trend_down":
            return lower
        return 0

    def toxicity(self, volatility: float) -> float:
        score = 0.0
        if volatility >= 2.0:
            score += 0.5
        if abs(self.imbalance) >= 0.45:
            score += 0.5
        return score

    def fair_value(
        self,
        regime: str,
        target_position: int,
        predicted_now: float,
        predicted_next: float,
        hybrid_alpha: float,
        style: Dict[str, float],
    ) -> float:
        line_gap = predicted_now - float(self.mid)
        scaled_imbalance = self.imbalance * (self.ALPHA_IMBALANCE_SCALE + style["imbalance_bonus"])
        fair = (
            self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
            + self.HISTORY_WEIGHT * float(self.recent_average)
            + self.REGRESSION_WEIGHT * predicted_next
            + self.IMBALANCE_WEIGHT * scaled_imbalance
        )
        fair += self.FAIR_ALPHA_WEIGHT * hybrid_alpha
        fair += (target_position - self.projected_position()) / self.POSITION_BIAS_DIVISOR
        if regime == "range":
            fair += self.RESIDUAL_REVERT_WEIGHT * line_gap
        else:
            fair += (0.10 * line_gap) + (self.TREND_FAIR_BONUS * (predicted_next - float(self.mid)))
        return fair

    def adjusted_fair_value(
        self,
        regime: str,
        target_position: int,
        predicted_now: float,
        predicted_next: float,
        hybrid_alpha: float,
        style: Dict[str, float],
    ) -> float:
        fair = self.fair_value(regime, target_position, predicted_now, predicted_next, hybrid_alpha, style)
        return fair - (self.projected_position() * self.INVENTORY_SKEW)

    def take_edge(
        self,
        side: str,
        regime: str,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
        style: Dict[str, float],
    ) -> float:
        edge = self.BASE_TAKE_EDGE

        if int(self.spread) >= 14:
            edge += 0.4

        position = self.projected_position()

        if side == "BUY":
            if position <= -20:
                edge -= 0.5
            elif position >= 20:
                edge += 0.5
        else:
            if position >= 20:
                edge -= 0.5
            elif position <= -20:
                edge += 0.5

        edge += 0.20 * self.toxicity(volatility)

        if regime == "trend_up":
            if side == "BUY":
                edge += -0.35 - self.TREND_BUY_TAKE_EXTRA
            else:
                edge += 0.55 + (0.50 * self.TREND_SELL_HOLD_EXTRA)
        elif regime == "trend_down":
            if side == "SELL":
                edge += -0.35 - self.TREND_BUY_TAKE_EXTRA
            else:
                edge += 0.55 + (0.50 * self.TREND_SELL_HOLD_EXTRA)
        elif regime == "volatile":
            edge += 0.50
        else:
            if side == "BUY" and predicted_edge <= -self.TREND_EDGE_THRESHOLD:
                edge += 0.35
            if side == "SELL" and predicted_edge >= self.TREND_EDGE_THRESHOLD:
                edge += 0.35

        if predicted_edge > 0 and side == "BUY":
            edge -= min(0.20, 0.05 * predicted_edge * max(0.5, fit_quality))
        elif predicted_edge < 0 and side == "SELL":
            edge -= min(0.20, 0.05 * abs(predicted_edge) * max(0.5, fit_quality))

        edge += style["take_edge_shift"]
        edge += self.inventory_pressure(side) * self.INVENTORY_EDGE_PRESSURE * 0.25
        return max(0.45, edge)

    def quote_edge(self, regime: str, volatility: float, fit_quality: float, style: Dict[str, float]) -> float:
        tau = self.time_fraction_remaining()
        gamma = self.control_gamma(regime)
        edge = max(self.BASE_QUOTE_EDGE, float(self.spread) / 3.5)
        edge = min(self.MAX_QUOTE_EDGE, edge)

        if abs(self.projected_position()) >= self.soft_limit:
            edge += 0.5

        if regime == "volatile":
            edge += 1.0
        elif regime in {"trend_up", "trend_down"}:
            edge += 0.15 + (0.10 * fit_quality)

        edge += self.SPREAD_VOL_COEF * min(3.0, volatility)
        edge += self.SPREAD_INV_COEF * gamma * min(self.position_limit, abs(self.projected_position()))
        edge += self.SPREAD_TIME_COEF * gamma * tau
        edge += self.inventory_pressure() * self.INVENTORY_EDGE_PRESSURE
        edge *= style["quote_mult"]
        return min(self.MAX_QUOTE_EDGE, edge)

    def passive_quotes(
        self,
        adjusted_fair: float,
        regime: str,
        target_position: int,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
        style: Dict[str, float],
        mode: str,
    ) -> Tuple[Optional[int], Optional[int]]:
        quote_edge = self.quote_edge(regime, volatility, fit_quality, style)
        buy_quote = math.floor(adjusted_fair - quote_edge)
        sell_quote = math.ceil(adjusted_fair + quote_edge)
        buy_quote, sell_quote = self.clamp_inside_spread(buy_quote, sell_quote)

        position = self.projected_position()
        if style["join_ticks"] > 0:
            if buy_quote is not None:
                buy_quote = min(int(self.best_ask) - 1, buy_quote + int(style["join_ticks"]))
            if sell_quote is not None:
                sell_quote = max(int(self.best_bid) + 1, sell_quote - int(style["join_ticks"]))
        if mode == "strong_up":
            sell_quote = None
            if buy_quote is not None:
                buy_quote = min(int(self.best_ask) - 1, max(int(self.best_bid) + 1, buy_quote + 1))
        elif mode == "strong_down":
            buy_quote = None
            if sell_quote is not None:
                sell_quote = max(int(self.best_bid) + 1, min(int(self.best_ask) - 1, sell_quote - 1))
        elif mode == "lean_up" and position <= target_position:
            sell_quote = None
        elif mode == "lean_down" and position >= target_position:
            buy_quote = None
        elif mode == "defensive":
            if position > 0:
                buy_quote = None
            elif position < 0:
                sell_quote = None
        if regime == "trend_up":
            if buy_quote is not None and position < target_position:
                buy_quote = min(
                    int(self.best_ask) - 1,
                    max(int(self.best_bid) + 1, buy_quote + int(self.TREND_PASSIVE_PUSH)),
                )
            if sell_quote is not None and position > 0:
                lift = 1 if predicted_edge >= self.TREND_EDGE_THRESHOLD else 0
                if predicted_edge >= self.STRONG_TREND_EDGE:
                    lift += 1
                lift += int(self.TREND_QUOTE_LIFT_EXTRA)
                sell_quote += lift
        elif regime == "trend_down":
            if sell_quote is not None and position > target_position:
                sell_quote = max(
                    int(self.best_bid) + 1,
                    min(int(self.best_ask) - 1, sell_quote - int(self.TREND_PASSIVE_PUSH)),
                )
            if buy_quote is not None and position < 0:
                drop = 1 if predicted_edge <= -self.TREND_EDGE_THRESHOLD else 0
                if predicted_edge <= -self.STRONG_TREND_EDGE:
                    drop += 1
                buy_quote -= drop
        elif regime == "volatile" and abs(position) <= 6:
            buy_quote = None
            sell_quote = None

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def passive_size(self, side: str, regime: str, volatility: float, style: Dict[str, float]) -> int:
        size = self.PASSIVE_SIZE
        if int(self.spread) >= 14:
            size += 1

        if regime == "volatile":
            size = max(1, size - 3)
        elif regime in {"trend_up", "trend_down"}:
            size = max(1, size + int(self.TREND_PASSIVE_SIZE_BONUS))

        size = max(1, int(size - self.toxicity(volatility)))

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

        size = int(round(size * max(0.45, 1.0 - (self.INVENTORY_SIZE_PRESSURE * self.inventory_pressure(side)))))
        if self.fill_quality_ewma > 0.25 and self.adverse_ewma < 0.35 and style["join_ticks"] > 0:
            size += 1
        if self.adverse_ewma > 0.45:
            size = max(1, size - 2)
        return size

    def allow_passive(self, side: str, regime: str) -> bool:
        position = self.projected_position()
        if side == "BUY" and position >= self.soft_limit:
            return False
        if side == "SELL" and position <= -self.soft_limit:
            return False
        if regime == "volatile" and abs(position) <= 6:
            return False
        if self.adverse_ewma > 0.75 and self.inventory_pressure(side) > 0.65:
            return False
        return True

    def take_orders(
        self,
        regime: str,
        target_position: int,
        adjusted_fair: float,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
        style: Dict[str, float],
        mode: str,
    ) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        if (
            int(self.best_ask) <= adjusted_fair - self.take_edge("BUY", regime, predicted_edge, fit_quality, volatility, style)
            and self.buy_capacity > 0
        ):
            take_limit = self.MAX_TAKE_SIZE + (int(self.TREND_ENTRY_TAKE_BONUS) if regime == "trend_up" else 0) + int(style["take_size_bonus"])
            if mode == "strong_up":
                take_limit += 2
            elif mode == "strong_down":
                take_limit = max(1, take_limit - 2)
            take_limit = max(1, int(round(take_limit * max(0.55, 1.0 - (0.35 * self.inventory_pressure("BUY"))))))
            if mode in {"lean_down", "strong_down", "defensive"}:
                pass
            elif regime != "range" and self.projected_position() >= target_position:
                pass
            else:
                quantity = min(self.best_ask_volume, take_limit)
                if regime != "range":
                    quantity = min(quantity, max(1, target_position - self.projected_position()))
                before = self.buy_capacity
                self.add_buy(int(self.best_ask), quantity)
                took_buy = self.buy_capacity < before

        if (
            int(self.best_bid) >= adjusted_fair + self.take_edge("SELL", regime, predicted_edge, fit_quality, volatility, style)
            and self.sell_capacity > 0
        ):
            take_limit = self.MAX_TAKE_SIZE + (int(self.TREND_ENTRY_TAKE_BONUS) if regime == "trend_down" else 0) + int(style["take_size_bonus"])
            if mode == "strong_down":
                take_limit += 2
            elif mode == "strong_up":
                take_limit = max(1, take_limit - 2)
            take_limit = max(1, int(round(take_limit * max(0.55, 1.0 - (0.35 * self.inventory_pressure("SELL"))))))
            required_bonus = 0.0
            if regime == "trend_up" and predicted_edge >= self.TREND_EDGE_THRESHOLD:
                required_bonus += self.TREND_HOLD_EXIT_BONUS + self.TREND_SELL_HOLD_EXTRA
            if regime == "trend_up" and predicted_edge >= self.STRONG_TREND_EDGE:
                required_bonus += self.STRONG_TREND_HOLD_EXIT_BONUS + self.TREND_SELL_HOLD_EXTRA
            required_bonus += self.HOLD_TIME_COEF * self.time_fraction_remaining()
            required_bonus += self.HOLD_VOL_COEF * min(3.0, volatility)
            if mode in {"lean_up", "strong_up", "defensive"} and self.projected_position() <= max(target_position, 0):
                pass
            elif regime != "range" and self.projected_position() <= target_position:
                pass
            elif int(self.best_bid) < adjusted_fair + self.take_edge("SELL", regime, predicted_edge, fit_quality, volatility, style) + required_bonus:
                pass
            else:
                quantity = min(self.best_bid_volume, take_limit)
                if regime != "range":
                    quantity = min(quantity, max(1, self.projected_position() - target_position))
                before = self.sell_capacity
                self.add_sell(int(self.best_bid), quantity)
                took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        self.update_state()
        self.update_fill_feedback()
        predicted_now, predicted_next, fit_quality, volatility = self.regression_metrics()
        provisional_style = {
            "micro_bonus": 0.0,
            "imbalance_bonus": 0.0,
            "alpha_bonus": 0.0,
            "quote_mult": 1.0,
            "join_ticks": 0.0,
            "take_edge_shift": 0.0,
            "take_size_bonus": 0.0,
            "target_bonus": 0.0,
        }
        _hybrid_fair, hybrid_alpha = self.hybrid_alpha(provisional_style)
        regression_edge = (predicted_next - float(self.mid)) * self.ALPHA_EDGE_SCALE
        provisional_edge = regression_edge
        provisional_next = float(self.mid) + provisional_edge
        provisional_regime = self.classify_state(provisional_edge, fit_quality, volatility)
        hybrid_alpha = self.guarded_hybrid_alpha(hybrid_alpha, regression_edge, provisional_regime)
        style = self.market_style(provisional_regime, provisional_edge, fit_quality, volatility)
        _hybrid_fair, hybrid_alpha = self.hybrid_alpha(style)
        hybrid_alpha = self.guarded_hybrid_alpha(hybrid_alpha, regression_edge, provisional_regime)
        predicted_edge = (
            (1.0 - self.ALPHA_BLEND_WEIGHT) * regression_edge
            + self.ALPHA_BLEND_WEIGHT * hybrid_alpha
        )
        mode_score = self.alpha_score(predicted_edge)
        self.mode = self.classify_mode(mode_score)
        predicted_next = float(self.mid) + predicted_edge
        regime = self.classify_state(predicted_edge, fit_quality, volatility)
        if self.mode == "defensive":
            regime = "volatile"
        elif self.mode in {"lean_up", "strong_up"} and regime == "range":
            regime = "trend_up"
        elif self.mode in {"lean_down", "strong_down"} and regime == "range":
            regime = "trend_down"
        style = self.market_style(regime, predicted_edge, fit_quality, volatility)
        target_position = self.target_position(regime, predicted_edge, fit_quality, style, self.mode)
        adjusted_fair = self.adjusted_fair_value(
            regime,
            target_position,
            predicted_now,
            predicted_next,
            hybrid_alpha,
            style,
        ) - self.reservation_adjustment(regime, target_position, predicted_edge, volatility)
        took_buy, took_sell = self.take_orders(
            regime,
            target_position,
            adjusted_fair,
            predicted_edge,
            fit_quality,
            volatility,
            style,
            self.mode,
        )

        buy_quote, sell_quote = self.passive_quotes(
            adjusted_fair,
            regime,
            target_position,
            predicted_edge,
            fit_quality,
            volatility,
            style,
            self.mode,
        )
        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.allow_passive("BUY", regime)
        ):
            if regime == "range" or position < target_position:
                quantity = min(self.passive_size("BUY", regime, volatility, style), self.buy_capacity)
                if regime != "range":
                    quantity = min(quantity, max(1, target_position - position))
                self.add_buy(buy_quote, quantity)

        position = self.projected_position()
        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.allow_passive("SELL", regime)
        ):
            if regime == "range" or position > target_position:
                quantity = min(self.passive_size("SELL", regime, volatility, style), self.sell_capacity)
                if regime != "range":
                    quantity = min(quantity, max(1, position - target_position))
                self.add_sell(sell_quote, quantity)

        self.memory = {
            "prev_mid": round(self.prev_mid, 4),
            "ewma_mid": round(self.ewma_mid, 4),
            "ewma_return": round(self.ewma_return, 4),
            "ewma_abs_return": round(self.ewma_abs_return, 4),
            "ewma_micro_gap": round(self.ewma_micro_gap, 4),
            "ewma_imbalance": round(self.ewma_imbalance, 4),
            "regime_score": round(self.regime_score, 4),
            "mode": self.mode,
            "fill_quality_ewma": round(self.fill_quality_ewma, 4),
            "adverse_ewma": round(self.adverse_ewma, 4),
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
