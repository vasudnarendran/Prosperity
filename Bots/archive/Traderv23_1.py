from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


DEFAULT_EMERALDS_PARAMS = {
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


DEFAULT_TOMATOES_PARAMS = {
    "CARRY_MID_WEIGHT": 0.25,
    "CARRY_MICRO_WEIGHT": 0.30,
    "CARRY_HISTORY_WEIGHT": 0.25,
    "CARRY_REGRESSION_WEIGHT": 0.20,
    "CARRY_RESIDUAL_REVERT_WEIGHT": 0.12,
    "CARRY_IMBALANCE_WEIGHT": 0.35,
    "CARRY_INVENTORY_SKEW": 0.035,
    "CARRY_BASE_TAKE_EDGE": 1.10,
    "CARRY_BASE_QUOTE_EDGE": 2.25,
    "CARRY_PASSIVE_SIZE": 8,
    "CARRY_MAX_TAKE_SIZE": 10,
    "REGRESSION_WINDOW": 8,
    "REGRESSION_HORIZON": 2.0,
    "TREND_EDGE_THRESHOLD": 1.00,
    "STRONG_TREND_EDGE": 2.50,
    "FIT_THRESHOLD": 0.45,
    "TREND_IMBALANCE_THRESHOLD": 0.12,
    "CARRY_POSITION_BIAS_DIVISOR": 12.0,
    "TREND_FAIR_BONUS": 0.25,
    "TREND_ENTRY_TAKE_BONUS": 3.0,
    "TREND_HOLD_EXIT_BONUS": 0.55,
    "STRONG_TREND_HOLD_EXIT_BONUS": 0.90,
    "TREND_PASSIVE_PUSH": 0.0,
    "TREND_PASSIVE_SIZE_BONUS": 2.0,
    "FADE_MID_WEIGHT": 0.20,
    "FADE_MICRO_WEIGHT": 0.25,
    "FADE_HISTORY_WEIGHT": 0.35,
    "FADE_SHORT_HISTORY_WEIGHT": 0.20,
    "FADE_WALL_WEIGHT": 0.00,
    "FADE_IMBALANCE_WEIGHT": 0.15,
    "FADE_INVENTORY_SKEW": 0.080,
    "FADE_BASE_TAKE_EDGE": 0.90,
    "FADE_BASE_QUOTE_EDGE": 1.80,
    "FADE_PASSIVE_SIZE": 9,
    "FADE_MAX_TAKE_SIZE": 12,
    "FADE_SCALE": 14.0,
    "FADE_MAX_TARGET": 48.0,
    "STRONG_FADE_TARGET": 64.0,
    "RANGE_DEVIATION_THRESHOLD": 1.40,
    "STRONG_DEVIATION_THRESHOLD": 2.60,
    "MOMENTUM_PENALTY": 0.45,
    "SHORT_MOMENTUM_PENALTY": 0.60,
    "TREND_PENALTY_SCALE": 0.55,
    "FADE_POSITION_BIAS_DIVISOR": 8.0,
    "VOL_WINDOW": 10,
    "MAX_QUOTE_EDGE": 5.0,
    "TOXIC_SPREAD_THRESHOLD": 15.0,
    "TOXIC_VOLATILITY_THRESHOLD": 3.0,
    "SOFT_LIMIT_RATIO": 0.60,
    "BASE_CARRY_WEIGHT": 0.55,
    "TREND_CARRY_BONUS": 0.20,
    "STRETCH_FADE_BONUS": 0.20,
    "VOLATILE_FADE_BONUS": 0.10,
    "HYBRID_QUOTE_BONUS": 0.0,
}


class BaseProductTrader:
    HISTORY_LENGTH = 8

    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
    ) -> None:
        self.product = product
        self.state = state
        self.mid_history = mid_history
        self.position_limit = position_limit
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
        self.bid_wall: Optional[int] = None
        self.ask_wall: Optional[int] = None
        self.wall_mid: Optional[float] = None
        self.mid: Optional[float] = None
        self.micro: Optional[float] = None
        self.spread: Optional[int] = None
        self.recent_average: Optional[float] = None
        self.short_average: Optional[float] = None
        self.momentum: float = 0.0
        self.short_momentum: float = 0.0
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
        self.bid_wall = self.buy_levels[-1][0] if self.buy_levels else None
        self.ask_wall = self.sell_levels[-1][0] if self.sell_levels else None
        self.wall_mid = (self.bid_wall + self.ask_wall) / 2 if self.bid_wall is not None and self.ask_wall is not None else None
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
        short_history = history[-3:]
        self.short_average = sum(short_history) / len(short_history) if short_history else self.mid
        self.momentum = self.mid - self.recent_average
        self.short_momentum = self.mid - self.short_average

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


class EmeraldsTrader(BaseProductTrader):
    PARAMETER_DEFAULTS = DEFAULT_EMERALDS_PARAMS

    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
        params: Optional[Dict[str, float]] = None,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit)
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
        params: Optional[Dict[str, float]] = None,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit)
        self.apply_parameter_overrides(self.PARAMETER_DEFAULTS, params)
        self.soft_limit = int(position_limit * self.SOFT_LIMIT_RATIO)

    def carry_regression_metrics(self) -> Tuple[float, float, float, float, float]:
        history = self.mid_history.get(self.product, [])
        window = history[-int(self.REGRESSION_WINDOW) :]
        if len(window) < 2:
            return 0.0, float(self.mid), float(self.mid), 0.0, 0.0

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
        return slope, predicted_now, predicted_next, fit_quality, volatility

    def carry_classify_state(
        self,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
    ) -> str:
        if float(self.spread) >= self.TOXIC_SPREAD_THRESHOLD and volatility >= self.TOXIC_VOLATILITY_THRESHOLD:
            return "volatile"
        if (
            predicted_edge >= self.TREND_EDGE_THRESHOLD
            and fit_quality >= self.FIT_THRESHOLD
            and self.imbalance >= self.TREND_IMBALANCE_THRESHOLD
            and self.momentum >= 0.75
            and float(self.micro) >= float(self.mid)
        ):
            return "trend_up"
        if (
            predicted_edge <= -self.TREND_EDGE_THRESHOLD
            and fit_quality >= self.FIT_THRESHOLD
            and self.imbalance <= -self.TREND_IMBALANCE_THRESHOLD
            and self.momentum <= -0.75
            and float(self.micro) <= float(self.mid)
        ):
            return "trend_down"
        return "range"

    def carry_target_band(self, regime: str, predicted_edge: float, fit_quality: float) -> Tuple[int, int]:
        conviction = abs(predicted_edge) * max(0.5, fit_quality)
        if regime == "trend_up":
            return (22, 44) if conviction >= self.STRONG_TREND_EDGE else (10, 28)
        if regime == "trend_down":
            return (-44, -22) if conviction >= self.STRONG_TREND_EDGE else (-28, -10)
        if regime == "volatile":
            return -6, 6
        return -14, 14

    def carry_target_position(self, regime: str, predicted_edge: float, fit_quality: float) -> int:
        lower, upper = self.carry_target_band(regime, predicted_edge, fit_quality)
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

    def realized_volatility(self) -> float:
        history = self.mid_history.get(self.product, [])
        if len(history) < 2:
            return 0.0
        diffs = [abs(history[index] - history[index - 1]) for index in range(1, len(history))]
        recent = diffs[-max(2, int(self.VOL_WINDOW)) :]
        return sum(recent) / len(recent)

    def fade_classify_state(self, deviation: float, normalized_deviation: float, volatility: float) -> str:
        if float(self.spread) >= self.TOXIC_SPREAD_THRESHOLD or volatility >= self.TOXIC_VOLATILITY_THRESHOLD:
            return "volatile"
        if abs(self.momentum) >= 2.0 and abs(self.short_momentum) >= 1.0 and abs(self.imbalance) >= 0.25:
            return "trend"
        if abs(normalized_deviation) >= self.RANGE_DEVIATION_THRESHOLD:
            return "stretch"
        return "range"

    def carry_fair_value(
        self,
        regime: str,
        target_position: int,
        predicted_now: float,
        predicted_next: float,
    ) -> float:
        line_gap = predicted_now - float(self.mid)
        fair = (
            self.CARRY_MID_WEIGHT * float(self.mid)
            + self.CARRY_MICRO_WEIGHT * float(self.micro)
            + self.CARRY_HISTORY_WEIGHT * float(self.recent_average)
            + self.CARRY_REGRESSION_WEIGHT * predicted_next
            + self.CARRY_IMBALANCE_WEIGHT * self.imbalance
        )
        fair += (target_position - self.projected_position()) / self.CARRY_POSITION_BIAS_DIVISOR
        if regime == "range":
            fair += self.CARRY_RESIDUAL_REVERT_WEIGHT * line_gap
        else:
            fair += (0.10 * line_gap) + (self.TREND_FAIR_BONUS * (predicted_next - float(self.mid)))
        return fair

    def carry_adjusted_fair_value(
        self,
        regime: str,
        target_position: int,
        predicted_now: float,
        predicted_next: float,
    ) -> float:
        fair = self.carry_fair_value(regime, target_position, predicted_now, predicted_next)
        return fair - (self.projected_position() * self.CARRY_INVENTORY_SKEW)

    def fade_fair_value(self, regime: str) -> float:
        fair = (
            self.FADE_MID_WEIGHT * float(self.mid)
            + self.FADE_MICRO_WEIGHT * float(self.micro)
            + self.FADE_HISTORY_WEIGHT * float(self.recent_average)
            + self.FADE_SHORT_HISTORY_WEIGHT * float(self.short_average)
            + self.FADE_WALL_WEIGHT * float(self.wall_mid if self.wall_mid is not None else self.mid)
            + self.FADE_IMBALANCE_WEIGHT * self.imbalance
        )
        if regime == "trend":
            fair += 0.10 * self.momentum
        return fair

    def fade_signal(
        self,
        regime: str,
        fair: float,
        volatility: float,
    ) -> Tuple[float, float]:
        raw_deviation = fair - float(self.mid)
        effective = raw_deviation

        if raw_deviation > 0:
            if self.momentum < 0:
                effective -= self.MOMENTUM_PENALTY * abs(self.momentum)
            if self.short_momentum < 0:
                effective -= self.SHORT_MOMENTUM_PENALTY * abs(self.short_momentum)
        elif raw_deviation < 0:
            if self.momentum > 0:
                effective += self.MOMENTUM_PENALTY * abs(self.momentum)
            if self.short_momentum > 0:
                effective += self.SHORT_MOMENTUM_PENALTY * abs(self.short_momentum)

        if regime == "trend":
            effective *= self.TREND_PENALTY_SCALE
        elif regime == "volatile":
            effective *= 0.35

        scale = max(1.0, volatility, float(self.spread) / 2.0)
        return effective, effective / scale

    def fade_target_position(
        self,
        regime: str,
        deviation: float,
        normalized_deviation: float,
    ) -> int:
        cap = self.FADE_MAX_TARGET
        if abs(normalized_deviation) >= self.STRONG_DEVIATION_THRESHOLD and regime != "volatile":
            cap = self.STRONG_FADE_TARGET
        if regime == "volatile":
            cap = min(cap, 20.0)
        elif regime == "trend":
            cap = min(cap, 32.0)

        target = int(round(deviation * self.FADE_SCALE))
        target = max(-int(cap), min(int(cap), target))

        if abs(target) <= 2 and regime == "range":
            return 0
        return target

    def fade_adjusted_fair_value(
        self,
        regime: str,
        target_position: int,
    ) -> float:
        fair = self.fade_fair_value(regime)
        fair += (target_position - self.projected_position()) / self.FADE_POSITION_BIAS_DIVISOR
        return fair - (self.projected_position() * self.FADE_INVENTORY_SKEW)

    def carry_take_edge(
        self,
        side: str,
        regime: str,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
    ) -> float:
        edge = self.CARRY_BASE_TAKE_EDGE

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
            edge += -0.35 if side == "BUY" else 0.55
        elif regime == "trend_down":
            edge += -0.35 if side == "SELL" else 0.55
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

        return max(0.5, edge)

    def fade_take_edge(
        self,
        side: str,
        regime: str,
        normalized_deviation: float,
        volatility: float,
    ) -> float:
        edge = self.FADE_BASE_TAKE_EDGE

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

        edge += 0.30 * self.toxicity(volatility)

        if regime == "trend":
            edge += 0.55
        elif regime == "volatile":
            edge += 0.50
        elif regime == "range":
            edge -= min(0.25, 0.06 * abs(normalized_deviation))

        if side == "BUY" and normalized_deviation > 0:
            edge -= min(0.35, 0.10 * abs(normalized_deviation))
        elif side == "SELL" and normalized_deviation < 0:
            edge -= min(0.35, 0.10 * abs(normalized_deviation))

        return max(0.5, edge)

    def carry_quote_edge(self, regime: str, volatility: float, fit_quality: float) -> float:
        edge = max(self.CARRY_BASE_QUOTE_EDGE, float(self.spread) / 3.5)
        edge = min(self.MAX_QUOTE_EDGE, edge)

        if abs(self.projected_position()) >= self.soft_limit:
            edge += 0.5

        if regime == "volatile":
            edge += 1.0
        elif regime in {"trend_up", "trend_down"}:
            edge += 0.15 + (0.10 * fit_quality)

        edge += 0.20 * min(2.0, volatility)
        return min(self.MAX_QUOTE_EDGE, edge)

    def fade_quote_edge(self, regime: str, normalized_deviation: float, volatility: float) -> float:
        edge = max(self.FADE_BASE_QUOTE_EDGE, float(self.spread) / 3.5)
        edge = min(self.MAX_QUOTE_EDGE, edge)

        if abs(self.projected_position()) >= self.soft_limit:
            edge += 0.5

        if regime == "volatile":
            edge += 1.0
        elif regime == "trend":
            edge += 0.75
        elif regime == "stretch":
            edge = max(1.0, edge - 0.35)

        edge += 0.20 * min(2.0, volatility)
        return min(self.MAX_QUOTE_EDGE, edge)

    def switch_view(self) -> Dict[str, float]:
        _slope, predicted_now, predicted_next, fit_quality, regression_volatility = self.carry_regression_metrics()
        realized_volatility = self.realized_volatility()
        volatility = max(realized_volatility, regression_volatility)
        predicted_edge = predicted_next - float(self.mid)

        carry_regime = self.carry_classify_state(predicted_edge, fit_quality, volatility)
        carry_target = self.carry_target_position(carry_regime, predicted_edge, fit_quality)
        carry_adjusted_fair = self.carry_adjusted_fair_value(
            carry_regime,
            carry_target,
            predicted_now,
            predicted_next,
        )

        fade_provisional_fair = self.fade_fair_value("range")
        _fade_deviation, provisional_normalized = self.fade_signal("range", fade_provisional_fair, volatility)
        fade_regime = self.fade_classify_state(_fade_deviation, provisional_normalized, volatility)
        fade_raw_fair = self.fade_fair_value(fade_regime)
        fade_deviation, fade_normalized = self.fade_signal(fade_regime, fade_raw_fair, volatility)
        fade_target = self.fade_target_position(fade_regime, fade_deviation, fade_normalized)
        fade_adjusted_fair = self.fade_adjusted_fair_value(fade_regime, fade_target)

        if carry_regime == "volatile" or fade_regime == "volatile":
            mode = "fade"
        elif carry_regime in {"trend_up", "trend_down"} and fit_quality >= self.FIT_THRESHOLD:
            mode = "carry"
        elif fade_regime in {"stretch", "range"}:
            mode = "fade"
        elif abs(predicted_edge) >= max(1.0, abs(fade_normalized)):
            mode = "carry"
        else:
            mode = "fade"

        if mode == "carry":
            target_position = carry_target
            adjusted_fair = carry_adjusted_fair
            buy_edge = self.carry_take_edge("BUY", carry_regime, predicted_edge, fit_quality, volatility)
            sell_edge = self.carry_take_edge("SELL", carry_regime, predicted_edge, fit_quality, volatility)
            quote_edge = self.carry_quote_edge(carry_regime, volatility, fit_quality)
            passive_size = int(self.CARRY_PASSIVE_SIZE)
            max_take_size = int(self.CARRY_MAX_TAKE_SIZE)
        else:
            target_position = fade_target
            adjusted_fair = fade_adjusted_fair
            buy_edge = self.fade_take_edge("BUY", fade_regime, fade_normalized, volatility)
            sell_edge = self.fade_take_edge("SELL", fade_regime, fade_normalized, volatility)
            quote_edge = self.fade_quote_edge(fade_regime, fade_normalized, volatility)
            passive_size = int(self.FADE_PASSIVE_SIZE)
            max_take_size = int(self.FADE_MAX_TAKE_SIZE)

        return {
            "mode": mode,
            "carry_regime": carry_regime,
            "fade_regime": fade_regime,
            "predicted_edge": predicted_edge,
            "fit_quality": fit_quality,
            "fade_normalized": fade_normalized,
            "target_position": target_position,
            "adjusted_fair": adjusted_fair,
            "buy_edge": buy_edge,
            "sell_edge": sell_edge,
            "quote_edge": quote_edge,
            "passive_size": passive_size,
            "max_take_size": max_take_size,
            "volatility": volatility,
        }

    def allow_passive(self, side: str, view: Dict[str, float]) -> bool:
        position = self.projected_position()
        if side == "BUY" and position >= self.soft_limit:
            return False
        if side == "SELL" and position <= -self.soft_limit:
            return False
        if (
            view["carry_regime"] == "volatile" or view["fade_regime"] == "volatile"
        ) and abs(position) <= 6:
            return False
        return True

    def take_orders(self, view: Dict[str, float]) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        target_position = int(view["target_position"])
        adjusted_fair = float(view["adjusted_fair"])
        buy_edge = float(view["buy_edge"])
        sell_edge = float(view["sell_edge"])
        take_limit = int(view["max_take_size"])
        position = self.projected_position()

        if target_position > position and self.buy_capacity > 0:
            if int(self.best_ask) <= adjusted_fair - buy_edge:
                quantity = min(self.best_ask_volume, take_limit, target_position - position)
                before = self.buy_capacity
                self.add_buy(int(self.best_ask), quantity)
                took_buy = self.buy_capacity < before
        elif target_position == 0 and position < 0 and self.buy_capacity > 0:
            if int(self.best_ask) <= adjusted_fair + buy_edge:
                quantity = min(abs(position), self.best_ask_volume, take_limit)
                before = self.buy_capacity
                self.add_buy(int(self.best_ask), quantity)
                took_buy = self.buy_capacity < before

        position = self.projected_position()
        if target_position < position and self.sell_capacity > 0:
            if int(self.best_bid) >= adjusted_fair + sell_edge:
                quantity = min(self.best_bid_volume, take_limit, position - target_position)
                before = self.sell_capacity
                self.add_sell(int(self.best_bid), quantity)
                took_sell = self.sell_capacity < before
        elif target_position == 0 and position > 0 and self.sell_capacity > 0:
            if int(self.best_bid) >= adjusted_fair - sell_edge:
                quantity = min(position, self.best_bid_volume, take_limit)
                before = self.sell_capacity
                self.add_sell(int(self.best_bid), quantity)
                took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def passive_quotes(self, view: Dict[str, float]) -> Tuple[Optional[int], Optional[int]]:
        adjusted_fair = float(view["adjusted_fair"])
        quote_edge = float(view["quote_edge"])
        target_position = int(view["target_position"])
        buy_quote = math.floor(adjusted_fair - quote_edge)
        sell_quote = math.ceil(adjusted_fair + quote_edge)
        buy_quote, sell_quote = self.clamp_inside_spread(buy_quote, sell_quote)

        position = self.projected_position()
        if (
            view["carry_regime"] == "volatile" or view["fade_regime"] == "volatile"
        ) and abs(position) <= 6:
            return None, None

        if buy_quote is not None and target_position > position:
            buy_quote = min(int(self.best_ask) - 1, max(int(self.best_bid) + 1, buy_quote + 1))
        if sell_quote is not None and target_position < position:
            sell_quote = max(int(self.best_bid) + 1, min(int(self.best_ask) - 1, sell_quote - 1))

        if (
            sell_quote is not None
            and position > 0
            and view["carry_regime"] == "trend_up"
            and float(view["predicted_edge"]) >= self.TREND_EDGE_THRESHOLD
        ):
            lift = 1 + (1 if float(view["predicted_edge"]) >= self.STRONG_TREND_EDGE else 0)
            sell_quote += lift

        if (
            buy_quote is not None
            and position < 0
            and view["carry_regime"] == "trend_down"
            and float(view["predicted_edge"]) <= -self.TREND_EDGE_THRESHOLD
        ):
            drop = 1 + (1 if float(view["predicted_edge"]) <= -self.STRONG_TREND_EDGE else 0)
            buy_quote -= drop

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        view = self.switch_view()
        took_buy, took_sell = self.take_orders(view)
        buy_quote, sell_quote = self.passive_quotes(view)
        target_position = int(view["target_position"])
        passive_size = int(view["passive_size"])
        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.allow_passive("BUY", view)
        ):
            if target_position > position:
                quantity = min(passive_size, self.buy_capacity, target_position - position)
                self.add_buy(buy_quote, quantity)
            elif target_position == 0 and view["fade_regime"] in {"range", "stretch"}:
                self.add_buy(buy_quote, min(passive_size, self.buy_capacity))

        position = self.projected_position()
        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.allow_passive("SELL", view)
        ):
            if target_position < position:
                quantity = min(passive_size, self.sell_capacity, position - target_position)
                self.add_sell(sell_quote, quantity)
            elif target_position == 0 and view["fade_regime"] in {"range", "stretch"}:
                self.add_sell(sell_quote, min(passive_size, self.sell_capacity))

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

    def load_trader_data(self, trader_data: str) -> Dict[str, List[float]]:
        if not trader_data:
            return {}
        try:
            parsed = json.loads(trader_data)
        except json.JSONDecodeError:
            return {}

        raw_history = parsed.get("mid_history", {})
        if not isinstance(raw_history, dict):
            return {}

        cleaned: Dict[str, List[float]] = {}
        for product, values in raw_history.items():
            if isinstance(values, list):
                cleaned[product] = [float(value) for value in values[-BaseProductTrader.HISTORY_LENGTH :]]
        return cleaned

    def build_trader_data(self, mid_history: Dict[str, List[float]]) -> str:
        return json.dumps({"mid_history": mid_history}, separators=(",", ":"))

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        mid_history = self.load_trader_data(state.traderData)

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
            )
            result[product] = trader.run()

        conversions = 0
        trader_data = self.build_trader_data(mid_history)
        return result, conversions, trader_data
