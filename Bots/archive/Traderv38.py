from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


DEFAULT_EMERALDS_PARAMS = {
    "REFERENCE_PRICE": 10000.0,
    "REFERENCE_WEIGHT": 0.82,
    "MID_WEIGHT": 0.18,
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
    # Physics-inspired drift model
    "ANCHOR_WINDOW": 16,
    "DRIFT_WINDOW": 4,
    "VELOCITY_WEIGHT": 1.20,
    "ACCEL_WEIGHT": 0.55,
    "DAMPING_WEIGHT": 0.22,
    "MICRO_WEIGHT": 0.65,
    "IMBALANCE_WEIGHT": 1.05,

    # Regime
    "TREND_THRESHOLD": 0.82,
    "VOLATILE_SPREAD_THRESHOLD": 15.0,
    "VOLATILE_VOL_THRESHOLD": 3.1,

    # HJB / AS-lite control
    "GAMMA_RANGE": 0.08,
    "GAMMA_TREND": 0.04,
    "GAMMA_VOLATILE": 0.14,
    "BASE_HALF_SPREAD": 1.65,
    "MIN_HALF_SPREAD": 1.35,
    "MAX_HALF_SPREAD": 6.0,
    "SPREAD_VOL_COEF": 0.62,
    "SPREAD_INV_COEF": 0.30,
    "SPREAD_VOLATILE_BONUS": 0.95,
    "TIME_HORIZON_TICKS": 10000.0,
    "TAU_FLOOR": 0.05,
    "SIGMA_FLOOR": 1.00,

    # Inventory / position
    "INVENTORY_SKEW": 0.015,
    "SOFT_LIMIT_RATIO_RANGE": 0.22,
    "SOFT_LIMIT_RATIO_TREND": 0.52,
    "SOFT_LIMIT_RATIO_VOLATILE": 0.10,

    # Execution
    "PASSIVE_SIZE": 8,
    "MAX_TAKE_SIZE": 10,
    "TAKE_EDGE_BASE": 0.72,
    "TAKE_VOL_COEF": 0.10,
    "TAKE_TREND_BONUS": 0.40,
    "TAKE_CHASE_PENALTY": 0.28,
    "TREND_QUOTE_SKEW": 0.12,
}


class BaseProductTrader:
    HISTORY_LENGTH = 30

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

        self.history: List[float] = list(mid_history.get(product, []))

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

        self.recent_average = sum(self.history) / len(self.history) if self.history else self.mid
        self.momentum = float(self.mid) - float(self.recent_average)

    def has_book(self) -> bool:
        return (
            self.best_bid is not None
            and self.best_ask is not None
            and self.mid is not None
            and self.micro is not None
        )

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

    def update_history(self) -> None:
        if self.mid is None:
            return
        self.history.append(float(self.mid))
        self.mid_history[self.product] = self.history[-self.HISTORY_LENGTH:]

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

        self.update_history()
        return self.orders


class TomatoesPhysicsTrader(BaseProductTrader):
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

    def time_fraction_remaining(self) -> float:
        timestamp = float(getattr(self.state, "timestamp", 0))
        remaining_ticks = max(0.0, self.TIME_HORIZON_TICKS - (timestamp / 100.0))
        tau = remaining_ticks / self.TIME_HORIZON_TICKS
        return max(self.TAU_FLOOR, tau)

    def realized_volatility(self) -> float:
        if len(self.history) < 2:
            return max(self.SIGMA_FLOOR, float(self.spread) / 2.0)
        diffs = [abs(self.history[i] - self.history[i - 1]) for i in range(1, len(self.history))]
        recent = diffs[-8:]
        return max(self.SIGMA_FLOOR, sum(recent) / max(1, len(recent)))

    def anchor_price(self) -> float:
        window = self.history[-int(self.ANCHOR_WINDOW):]
        if not window:
            return float(self.mid)
        return sum(window) / len(window)

    def normalized_stretch(self, stretch: float, volatility: float) -> float:
        return stretch / max(1.0, volatility)

    def velocity(self) -> float:
        if len(self.history) < 1:
            return 0.0
        current = float(self.mid)
        prev = float(self.history[-1])
        return current - prev

    def avg_velocity(self) -> float:
        if len(self.history) < 2:
            return self.velocity()
        points = self.history[-int(self.DRIFT_WINDOW):] + [float(self.mid)]
        diffs = [points[i] - points[i - 1] for i in range(1, len(points))]
        return sum(diffs) / len(diffs) if diffs else 0.0

    def acceleration(self) -> float:
        if len(self.history) < 2:
            return 0.0
        last_vel = float(self.history[-1]) - float(self.history[-2])
        return self.velocity() - last_vel

    def drift_signal(self) -> Tuple[float, float]:
        vel = self.avg_velocity()
        acc = self.acceleration()
        anchor = self.anchor_price()
        stretch = float(self.mid) - anchor
        micro_gap = float(self.micro) - float(self.mid)

        drift = (
            self.VELOCITY_WEIGHT * vel
            + self.ACCEL_WEIGHT * acc
            - self.DAMPING_WEIGHT * stretch
            + self.MICRO_WEIGHT * micro_gap
            + self.IMBALANCE_WEIGHT * float(self.imbalance)
        )
        return drift, stretch

    def classify_regime(self, drift: float, volatility: float) -> str:
        if (
            float(self.spread) >= self.VOLATILE_SPREAD_THRESHOLD
            and volatility >= self.VOLATILE_VOL_THRESHOLD
        ):
            return "volatile"

        up_confirm = self.imbalance > 0.05 and float(self.micro) >= float(self.mid)
        down_confirm = self.imbalance < -0.05 and float(self.micro) <= float(self.mid)

        if drift >= self.TREND_THRESHOLD and up_confirm:
            return "trend_up"
        if drift <= -self.TREND_THRESHOLD and down_confirm:
            return "trend_down"
        return "range"

    def regime_gamma(self, regime: str) -> float:
        if regime in {"trend_up", "trend_down"}:
            return self.GAMMA_TREND
        if regime == "volatile":
            return self.GAMMA_VOLATILE
        return self.GAMMA_RANGE

    def regime_soft_limit(self, regime: str) -> int:
        if regime in {"trend_up", "trend_down"}:
            ratio = self.SOFT_LIMIT_RATIO_TREND
        elif regime == "volatile":
            ratio = self.SOFT_LIMIT_RATIO_VOLATILE
        else:
            ratio = self.SOFT_LIMIT_RATIO_RANGE
        return max(6, int(self.position_limit * ratio))

    def target_position(self, regime: str, drift: float, stretch: float, volatility: float) -> int:
        soft_limit = self.regime_soft_limit(regime)
        norm_stretch = self.normalized_stretch(stretch, volatility)

        if regime == "trend_up":
            conviction = min(1.0, abs(drift) / 2.0)
            target = int(round(soft_limit * conviction))
            if norm_stretch > 1.5:
                target = int(round(0.75 * target))
            return target
        if regime == "trend_down":
            conviction = min(1.0, abs(drift) / 2.0)
            target = -int(round(soft_limit * conviction))
            if norm_stretch < -1.5:
                target = int(round(0.75 * target))
            return target
        if regime == "volatile":
            return 0

        return int(round(-0.25 * soft_limit * max(-1.0, min(1.0, norm_stretch))))

    def fair_value(self, drift: float) -> float:
        return float(self.mid) + drift

    def reservation_price(
        self,
        fair: float,
        regime: str,
        target_position: int,
        volatility: float,
    ) -> float:
        position_gap = self.projected_position() - target_position
        gamma = self.regime_gamma(regime)
        sigma = max(self.SIGMA_FLOOR, volatility)
        tau = self.time_fraction_remaining()

        # HJB / AS-lite inventory shift
        reservation = fair - (position_gap * gamma * (sigma ** 2) * tau)

        # very light direct inventory skew to keep it practical
        reservation -= position_gap * self.INVENTORY_SKEW
        return reservation

    def optimal_half_spread(
        self,
        regime: str,
        target_position: int,
        volatility: float,
    ) -> float:
        sigma = max(self.SIGMA_FLOOR, volatility)
        tau = self.time_fraction_remaining()
        inv_ratio = abs(self.projected_position() - target_position) / max(1, self.regime_soft_limit(regime))

        half_spread = self.BASE_HALF_SPREAD
        half_spread += self.SPREAD_VOL_COEF * min(3.0, sigma)
        half_spread += self.SPREAD_INV_COEF * min(1.0, inv_ratio)

        # HJB-lite term
        half_spread += 0.5 * self.regime_gamma(regime) * (sigma ** 2) * tau

        if regime == "volatile":
            half_spread += self.SPREAD_VOLATILE_BONUS

        return max(self.MIN_HALF_SPREAD, min(self.MAX_HALF_SPREAD, half_spread))

    def take_threshold(
        self,
        side: str,
        regime: str,
        drift: float,
        stretch: float,
        target_position: int,
        volatility: float,
        half_spread: float,
    ) -> float:
        threshold = self.TAKE_EDGE_BASE + self.TAKE_VOL_COEF * min(3.0, volatility)
        threshold = min(threshold, 0.78 * half_spread)

        position_gap = self.projected_position() - target_position
        if side == "BUY" and position_gap < 0:
            threshold -= 0.18
        elif side == "SELL" and position_gap > 0:
            threshold -= 0.18

        if regime == "trend_up" and side == "BUY":
            threshold -= self.TAKE_TREND_BONUS
        elif regime == "trend_down" and side == "SELL":
            threshold -= self.TAKE_TREND_BONUS

        norm_stretch = self.normalized_stretch(stretch, volatility)

        # physics-inspired chase penalty: do not chase if already stretched in same direction
        if side == "BUY" and drift > 0 and norm_stretch > 1.2:
            threshold += self.TAKE_CHASE_PENALTY
        elif side == "SELL" and drift < 0 and norm_stretch < -1.2:
            threshold += self.TAKE_CHASE_PENALTY

        if regime == "volatile":
            threshold += 0.25

        return max(0.30, threshold)

    def take_orders(
        self,
        fair: float,
        regime: str,
        drift: float,
        stretch: float,
        target_position: int,
        volatility: float,
        half_spread: float,
    ) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        buy_threshold = self.take_threshold(
            "BUY", regime, drift, stretch, target_position, volatility, half_spread
        )
        sell_threshold = self.take_threshold(
            "SELL", regime, drift, stretch, target_position, volatility, half_spread
        )

        for price, volume in self.sell_levels[:3]:
            if self.buy_capacity <= 0:
                break
            edge = fair - float(price)
            if edge < buy_threshold:
                break

            desired = max(0, target_position - self.projected_position())
            quantity = min(int(volume), self.buy_capacity, int(self.MAX_TAKE_SIZE))
            if regime != "range":
                quantity = min(quantity, max(1, desired))
            if quantity <= 0:
                continue

            before = self.buy_capacity
            self.add_buy(int(price), quantity)
            if self.buy_capacity < before:
                took_buy = True

        for price, volume in self.buy_levels[:3]:
            if self.sell_capacity <= 0:
                break
            edge = float(price) - fair
            if edge < sell_threshold:
                break

            desired = max(0, self.projected_position() - target_position)
            quantity = min(int(volume), self.sell_capacity, int(self.MAX_TAKE_SIZE))
            if regime != "range":
                quantity = min(quantity, max(1, desired))
            if quantity <= 0:
                continue

            before = self.sell_capacity
            self.add_sell(int(price), quantity)
            if self.sell_capacity < before:
                took_sell = True

        return took_buy, took_sell

    def passive_quotes(
        self,
        reservation: float,
        half_spread: float,
        regime: str,
        drift: float,
        target_position: int,
    ) -> Tuple[Optional[int], Optional[int]]:
        center = reservation

        # modest directional skew
        if regime == "trend_up":
            center += self.TREND_QUOTE_SKEW * min(1.0, drift / max(1.0, self.TREND_THRESHOLD))
        elif regime == "trend_down":
            center -= self.TREND_QUOTE_SKEW * min(1.0, abs(drift) / max(1.0, self.TREND_THRESHOLD))

        buy_quote = math.floor(center - half_spread)
        sell_quote = math.ceil(center + half_spread)

        position_gap = self.projected_position() - target_position
        if position_gap > max(2, self.regime_soft_limit(regime) // 3):
            buy_quote -= 1
            sell_quote -= 1
        elif position_gap < -max(2, self.regime_soft_limit(regime) // 3):
            buy_quote += 1
            sell_quote += 1

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def passive_size(self, side: str, regime: str, target_position: int) -> int:
        size = int(self.PASSIVE_SIZE)
        volatility = self.realized_volatility()
        drift, stretch = self.drift_signal()
        norm_stretch = abs(self.normalized_stretch(stretch, volatility))

        if regime == "volatile":
            size = max(1, size - 3)
        elif regime in {"trend_up", "trend_down"}:
            size += 1

        if norm_stretch > 1.4:
            size = max(1, size - 2)

        pos_gap = self.projected_position() - target_position
        if side == "BUY":
            if pos_gap < 0:
                size += 1
            elif pos_gap > 0:
                size = max(1, size - 2)
        else:
            if pos_gap > 0:
                size += 1
            elif pos_gap < 0:
                size = max(1, size - 2)

        return max(1, size)

    def allow_passive(self, side: str, regime: str, target_position: int) -> bool:
        pos = self.projected_position()
        soft_limit = self.regime_soft_limit(regime)
        volatility = self.realized_volatility()
        drift, stretch = self.drift_signal()
        norm_stretch = self.normalized_stretch(stretch, volatility)

        if regime == "volatile" and abs(pos) <= 4:
            return False
        if side == "BUY" and pos >= soft_limit:
            return False
        if side == "SELL" and pos <= -soft_limit:
            return False

        if regime == "trend_up" and side == "SELL" and pos <= 0:
            return False
        if regime == "trend_down" and side == "BUY" and pos >= 0:
            return False

        if side == "BUY" and drift < 0 and norm_stretch > 1.3:
            return False
        if side == "SELL" and drift > 0 and norm_stretch < -1.3:
            return False

        return True

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        volatility = self.realized_volatility()
        drift, stretch = self.drift_signal()
        regime = self.classify_regime(drift, volatility)
        target_position = self.target_position(regime, drift, stretch, volatility)

        fair = self.fair_value(drift)
        reservation = self.reservation_price(fair, regime, target_position, volatility)
        half_spread = self.optimal_half_spread(regime, target_position, volatility)

        took_buy, took_sell = self.take_orders(
            fair,
            regime,
            drift,
            stretch,
            target_position,
            volatility,
            half_spread,
        )

        reservation = self.reservation_price(fair, regime, target_position, volatility)
        buy_quote, sell_quote = self.passive_quotes(
            reservation,
            half_spread,
            regime,
            drift,
            target_position,
        )

        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.allow_passive("BUY", regime, target_position)
        ):
            if regime == "range" or position < target_position:
                quantity = min(self.passive_size("BUY", regime, target_position), self.buy_capacity)
                if regime != "range":
                    quantity = min(quantity, max(1, target_position - position))
                self.add_buy(buy_quote, quantity)

        position = self.projected_position()
        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.allow_passive("SELL", regime, target_position)
        ):
            if regime == "range" or position > target_position:
                quantity = min(self.passive_size("SELL", regime, target_position), self.sell_capacity)
                if regime != "range":
                    quantity = min(quantity, max(1, position - target_position))
                self.add_sell(sell_quote, quantity)

        self.update_history()
        return self.orders


class Trader:
    POSITION_LIMITS: Dict[str, int] = {
        "EMERALDS": 80,
        "TOMATOES": 80,
    }

    PRODUCT_TRADERS = {
        "EMERALDS": EmeraldsTrader,
        "TOMATOES": TomatoesPhysicsTrader,
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
                cleaned[product] = [float(v) for v in values[-BaseProductTrader.HISTORY_LENGTH:]]
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
