from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


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
        self.realized_vol: float = 0.0
        self.return_std: float = 0.0
        self.ma_slope: float = 0.0
        self.trend_consistency: float = 0.0
        self.drawdown_up: float = 0.0
        self.drawdown_down: float = 0.0
        self.volume_ratio: float = 1.0

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

        full_series = (history + [self.mid])[-self.HISTORY_LENGTH :]
        diffs = [full_series[index] - full_series[index - 1] for index in range(1, len(full_series))]
        abs_diffs = [abs(diff) for diff in diffs]
        self.realized_vol = (
            sum(abs_diffs) / len(abs_diffs)
            if abs_diffs
            else max(0.5, float(self.spread) / 2.0)
        )
        if diffs:
            mean_diff = sum(diffs) / len(diffs)
            self.return_std = math.sqrt(sum((diff - mean_diff) ** 2 for diff in diffs) / len(diffs))
            signed_steps = sum(1 if diff > 0 else -1 if diff < 0 else 0 for diff in diffs)
            self.trend_consistency = abs(signed_steps) / len(diffs)
        else:
            self.return_std = self.realized_vol
            self.trend_consistency = 0.0

        self.ma_slope = self.short_average - self.recent_average
        roll_high = max(full_series)
        roll_low = min(full_series)
        roll_range = max(1e-6, roll_high - roll_low)
        self.drawdown_up = (roll_high - self.mid) / roll_range
        self.drawdown_down = (self.mid - roll_low) / roll_range
        self.volume_ratio = self.best_bid_volume / max(1.0, float(self.best_ask_volume))

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
    REFERENCE_PRICE = 10000.0
    REFERENCE_WEIGHT = 0.80
    MID_WEIGHT = 0.20
    MICRO_WEIGHT = 0.00
    INVENTORY_SKEW = 0.12
    BASE_TAKE_EDGE = 1.00
    BASE_QUOTE_EDGE = 2.0
    MAX_QUOTE_EDGE = 4.0
    MAX_TAKE_SIZE = 10
    PASSIVE_SIZE = 7

    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit)
        self.soft_limit = int(position_limit * 0.5)

    def fair_value(self) -> float:
        return (
            self.REFERENCE_WEIGHT * self.REFERENCE_PRICE
            + self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
        )

    def adjusted_fair_value(self) -> float:
        return self.fair_value() - (self.projected_position() * self.INVENTORY_SKEW)

    def take_edge(self, side: str) -> float:
        edge = self.BASE_TAKE_EDGE
        position = self.projected_position()

        if int(self.spread) >= 14:
            edge += 0.5

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

        if side == "SELL" and int(self.best_bid) >= 10000:
            edge -= 0.25

        return max(0.5, edge)

    def quote_edge(self) -> float:
        edge = max(self.BASE_QUOTE_EDGE, float(self.spread) / 4.0)
        edge = min(self.MAX_QUOTE_EDGE, edge)

        if abs(self.projected_position()) >= self.soft_limit:
            edge += 0.5

        if int(self.best_ask) <= 10000 or int(self.best_bid) >= 10000:
            edge = max(1.5, edge - 0.5)

        return min(self.MAX_QUOTE_EDGE, edge)

    def passive_quotes(self, adjusted_fair: float) -> Tuple[Optional[int], Optional[int]]:
        buy_quote = math.floor(adjusted_fair - self.quote_edge())
        sell_quote = math.ceil(adjusted_fair + self.quote_edge())

        position = self.projected_position()
        if position >= self.soft_limit:
            sell_quote -= 1
        elif position <= -self.soft_limit:
            buy_quote += 1

        if int(self.best_bid) >= self.REFERENCE_PRICE and position >= 0:
            sell_quote += 1

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def passive_size(self, side: str) -> int:
        size = self.PASSIVE_SIZE
        if int(self.spread) >= 8:
            size += 1

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

        return max(1, size)

    def take_orders(self, adjusted_fair: float) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        if int(self.best_ask) <= adjusted_fair - self.take_edge("BUY") and self.buy_capacity > 0:
            before = self.buy_capacity
            self.add_buy(int(self.best_ask), min(self.best_ask_volume, self.MAX_TAKE_SIZE))
            took_buy = self.buy_capacity < before

        if int(self.best_bid) >= adjusted_fair + self.take_edge("SELL") and self.sell_capacity > 0:
            before = self.sell_capacity
            self.add_sell(int(self.best_bid), min(self.best_bid_volume, self.MAX_TAKE_SIZE))
            took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        adjusted_fair = self.adjusted_fair_value()
        took_buy, took_sell = self.take_orders(adjusted_fair)
        buy_quote, sell_quote = self.passive_quotes(adjusted_fair)
        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and position < self.soft_limit
        ):
            self.add_buy(buy_quote, self.passive_size("BUY"))

        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and position > -self.soft_limit
        ):
            self.add_sell(sell_quote, self.passive_size("SELL"))

        return self.orders


class TomatoesTrader(BaseProductTrader):
    MID_WEIGHT = 0.35
    MICRO_WEIGHT = 0.35
    HISTORY_WEIGHT = 0.30
    MOMENTUM_WEIGHT = 0.20
    IMBALANCE_WEIGHT = 0.70
    INVENTORY_SKEW = 0.08
    BASE_TAKE_EDGE = 1.35
    BASE_QUOTE_EDGE = 2.0
    MAX_QUOTE_EDGE = 5.0
    PASSIVE_SIZE = 7
    MAX_TAKE_SIZE = 8

    def clamp_prob(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def regime_probabilities(self) -> Tuple[Dict[str, float], int]:
        slope_strength = self.clamp_prob(abs(self.ma_slope) / 1.2)
        momentum_strength = self.clamp_prob(abs(self.momentum) / 2.5)
        imbalance_strength = self.clamp_prob(abs(self.imbalance) / 0.35)
        vol_strength = self.clamp_prob(self.realized_vol / 2.2)
        spread_strength = self.clamp_prob(float(self.spread) / 15.0)
        drawdown_strength = self.clamp_prob(max(self.drawdown_up, self.drawdown_down))

        trend_score = (
            0.28 * slope_strength
            + 0.24 * momentum_strength
            + 0.18 * imbalance_strength
            + 0.18 * self.trend_consistency
            + 0.12 * self.clamp_prob(abs(self.short_momentum) / 1.5)
        )
        high_vol_score = (
            0.40 * vol_strength
            + 0.28 * spread_strength
            + 0.20 * drawdown_strength
            + 0.12 * self.clamp_prob(self.return_std / 2.0)
        )
        range_score = (
            0.55 * (1.0 - slope_strength)
            + 0.20 * (1.0 - imbalance_strength)
            + 0.15 * (1.0 - vol_strength)
            + 0.10 * (1.0 - self.trend_consistency)
        )

        deviation = abs(self.mid - self.recent_average)
        if deviation > max(0.8, 1.2 * self.realized_vol):
            range_score *= 0.85

        raw = {
            "trend": max(0.05, trend_score),
            "range": max(0.05, range_score),
            "high_vol": max(0.05, high_vol_score),
        }
        total = sum(raw.values())
        probabilities = {name: value / total for name, value in raw.items()}

        trend_signal = (0.9 * self.ma_slope) + (0.6 * self.momentum) + (1.6 * self.imbalance)
        if trend_signal > 0.2:
            trend_direction = 1
        elif trend_signal < -0.2:
            trend_direction = -1
        else:
            trend_direction = 0

        return probabilities, trend_direction

    def risk_scale(self, probabilities: Dict[str, float]) -> float:
        vol_penalty = 0.60 * probabilities["high_vol"] + 0.18 * self.clamp_prob(self.realized_vol / 2.5)
        return max(0.25, min(1.0, 1.0 - vol_penalty))

    def confidence(self, probabilities: Dict[str, float]) -> float:
        return max(probabilities["trend"], probabilities["range"])

    def kill_switch(self, probabilities: Dict[str, float]) -> bool:
        return (
            probabilities["high_vol"] >= 0.85
            and self.realized_vol >= 3.0
            and float(self.spread) >= 14
            and abs(self.projected_position()) <= 10
        )

    def target_position(self, probabilities: Dict[str, float], trend_direction: int) -> int:
        confidence = self.confidence(probabilities)
        risk_scale = self.risk_scale(probabilities)
        trend_cap = max(10, int((26 + 10 * confidence) * risk_scale))
        range_cap = max(2, int((4 + 6 * confidence) * risk_scale))

        trend_target = 0
        if trend_direction != 0:
            trend_target = trend_direction * int(round(probabilities["trend"] * trend_cap))

        deviation = self.mid - self.recent_average
        range_target = 0
        if abs(deviation) > max(1.0, 1.2 * self.realized_vol):
            range_direction = -1 if deviation > 0 else 1
            range_target = range_direction * int(round(probabilities["range"] * range_cap))

        combined = trend_target + range_target
        if probabilities["high_vol"] >= 0.60:
            combined = int(round(combined * max(0.65, 1.0 - 0.35 * probabilities["high_vol"])))

        hard_cap = max(8, int(36 * risk_scale))
        return max(-hard_cap, min(hard_cap, combined))

    def toxicity(self) -> float:
        score = 0.0
        if abs(self.momentum) >= 2.0:
            score += 0.5
        if abs(self.imbalance) >= 0.45:
            score += 0.5
        return score

    def fair_value(self, target_position: int, probabilities: Dict[str, float], trend_direction: int) -> float:
        fair = (
            self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
            + self.HISTORY_WEIGHT * float(self.recent_average)
            + self.MOMENTUM_WEIGHT * self.momentum
            + self.IMBALANCE_WEIGHT * self.imbalance
        )
        fair += (target_position - self.projected_position()) / 18.0

        if trend_direction != 0:
            fair += trend_direction * probabilities["trend"] * min(0.8, abs(self.ma_slope))

        deviation = self.mid - self.recent_average
        if abs(deviation) > max(0.8, self.realized_vol):
            fair -= math.copysign(
                min(0.5, abs(deviation) * 0.12) * probabilities["range"],
                deviation,
            )

        return fair

    def adjusted_fair_value(self, target_position: int, probabilities: Dict[str, float], trend_direction: int) -> float:
        return self.fair_value(target_position, probabilities, trend_direction) - (
            self.projected_position() * self.INVENTORY_SKEW
        )

    def take_edge(self, side: str, probabilities: Dict[str, float], trend_direction: int) -> float:
        edge = self.BASE_TAKE_EDGE

        if int(self.spread) >= 14:
            edge += 0.5

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

        edge += 0.20 * self.toxicity()
        edge += 0.70 * probabilities["high_vol"]

        aligned = (side == "BUY" and trend_direction > 0) or (side == "SELL" and trend_direction < 0)
        opposed = (side == "BUY" and trend_direction < 0) or (side == "SELL" and trend_direction > 0)
        if aligned:
            edge -= 0.50 * probabilities["trend"]
        elif opposed:
            edge += 0.80 * probabilities["trend"]

        deviation = self.mid - self.recent_average
        if side == "BUY" and deviation < -max(0.8, self.realized_vol):
            edge -= 0.25 * probabilities["range"]
        if side == "SELL" and deviation > max(0.8, self.realized_vol):
            edge -= 0.25 * probabilities["range"]

        return max(0.5, edge)

    def quote_edge(self, probabilities: Dict[str, float]) -> float:
        edge = max(self.BASE_QUOTE_EDGE, float(self.spread) / 3.5)
        edge = min(self.MAX_QUOTE_EDGE, edge)

        if abs(self.projected_position()) >= self.soft_limit:
            edge += 0.5

        edge += 0.95 * probabilities["high_vol"]
        edge += 0.15 * probabilities["trend"]
        edge -= 0.20 * probabilities["range"]
        edge += 0.35 * self.toxicity()
        return min(self.MAX_QUOTE_EDGE, edge)

    def passive_quotes(
        self,
        adjusted_fair: float,
        probabilities: Dict[str, float],
        trend_direction: int,
        target_position: int,
        kill_switch_active: bool,
    ) -> Tuple[Optional[int], Optional[int]]:
        buy_quote = math.floor(adjusted_fair - self.quote_edge(probabilities))
        sell_quote = math.ceil(adjusted_fair + self.quote_edge(probabilities))
        buy_quote, sell_quote = self.clamp_inside_spread(buy_quote, sell_quote)

        position = self.projected_position()
        if kill_switch_active and abs(position) <= 8:
            return None, None

        if probabilities["trend"] >= probabilities["range"] + 0.10 and trend_direction > 0:
            if buy_quote is not None and position < target_position:
                buy_quote = min(int(self.best_ask) - 1, max(int(self.best_bid) + 1, buy_quote + 1))
            if position <= max(10, int(0.45 * max(1, target_position))):
                sell_quote = None
        elif probabilities["trend"] >= probabilities["range"] + 0.10 and trend_direction < 0:
            if sell_quote is not None and position > target_position:
                sell_quote = max(int(self.best_bid) + 1, min(int(self.best_ask) - 1, sell_quote - 1))
            if position >= min(-10, int(0.45 * min(-1, target_position))):
                buy_quote = None
        elif probabilities["high_vol"] >= 0.65 and abs(position) <= 6:
            buy_quote = None
            sell_quote = None

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def passive_size(
        self,
        side: str,
        probabilities: Dict[str, float],
        trend_direction: int,
        target_position: int,
    ) -> int:
        confidence = self.confidence(probabilities)
        risk_scale = self.risk_scale(probabilities)
        size = max(1, int(round(self.PASSIVE_SIZE * (0.55 + 0.55 * confidence) * risk_scale)))
        if int(self.spread) >= 14:
            size += 1

        if probabilities["high_vol"] >= 0.60:
            size = max(1, size - 2)
        elif probabilities["trend"] >= 0.50:
            size = max(1, size - 1)

        size = max(1, int(size - self.toxicity()))

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

        if side == "BUY" and trend_direction > 0 and position < target_position:
            size += 1
        if side == "SELL" and trend_direction < 0 and position > target_position:
            size += 1

        return size

    def allow_passive(self, side: str, probabilities: Dict[str, float], kill_switch_active: bool) -> bool:
        position = self.projected_position()
        if side == "BUY" and position >= self.soft_limit:
            return False
        if side == "SELL" and position <= -self.soft_limit:
            return False
        if kill_switch_active and abs(position) <= 10:
            return False
        if probabilities["high_vol"] >= 0.70 and abs(position) <= 6:
            return False
        return True

    def take_orders(
        self,
        probabilities: Dict[str, float],
        trend_direction: int,
        target_position: int,
        adjusted_fair: float,
        kill_switch_active: bool,
    ) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False
        confidence = self.confidence(probabilities)
        risk_scale = self.risk_scale(probabilities)

        if int(self.best_ask) <= adjusted_fair - self.take_edge("BUY", probabilities, trend_direction) and self.buy_capacity > 0:
            base_take_limit = max(2, int(round(self.MAX_TAKE_SIZE * (0.50 + 0.55 * confidence) * risk_scale)))
            take_limit = base_take_limit + (2 if trend_direction > 0 and probabilities["trend"] >= probabilities["range"] else 0)
            if kill_switch_active and self.projected_position() >= 0:
                pass
            elif probabilities["trend"] >= probabilities["range"] and self.projected_position() >= target_position:
                pass
            else:
                quantity = min(self.best_ask_volume, take_limit)
                if probabilities["trend"] >= probabilities["range"]:
                    quantity = min(quantity, max(1, target_position - self.projected_position()))
                before = self.buy_capacity
                self.add_buy(int(self.best_ask), quantity)
                took_buy = self.buy_capacity < before

        if int(self.best_bid) >= adjusted_fair + self.take_edge("SELL", probabilities, trend_direction) and self.sell_capacity > 0:
            base_take_limit = max(2, int(round(self.MAX_TAKE_SIZE * (0.50 + 0.55 * confidence) * risk_scale)))
            take_limit = base_take_limit + (2 if trend_direction < 0 and probabilities["trend"] >= probabilities["range"] else 0)
            if kill_switch_active and self.projected_position() <= 0:
                pass
            elif probabilities["trend"] >= probabilities["range"] and self.projected_position() <= target_position:
                pass
            else:
                quantity = min(self.best_bid_volume, take_limit)
                if probabilities["trend"] >= probabilities["range"]:
                    quantity = min(quantity, max(1, self.projected_position() - target_position))
                before = self.sell_capacity
                self.add_sell(int(self.best_bid), quantity)
                took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        probabilities, trend_direction = self.regime_probabilities()
        target_position = self.target_position(probabilities, trend_direction)
        kill_switch_active = self.kill_switch(probabilities)
        adjusted_fair = self.adjusted_fair_value(target_position, probabilities, trend_direction)
        took_buy, took_sell = self.take_orders(
            probabilities,
            trend_direction,
            target_position,
            adjusted_fair,
            kill_switch_active,
        )

        buy_quote, sell_quote = self.passive_quotes(
            adjusted_fair,
            probabilities,
            trend_direction,
            target_position,
            kill_switch_active,
        )
        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.allow_passive("BUY", probabilities, kill_switch_active)
        ):
            if probabilities["trend"] < probabilities["range"] or position < target_position:
                quantity = min(
                    self.passive_size("BUY", probabilities, trend_direction, target_position),
                    self.buy_capacity,
                )
                if probabilities["trend"] >= probabilities["range"]:
                    quantity = min(quantity, max(1, target_position - position))
                self.add_buy(buy_quote, quantity)

        position = self.projected_position()
        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.allow_passive("SELL", probabilities, kill_switch_active)
        ):
            if probabilities["trend"] < probabilities["range"] or position > target_position:
                quantity = min(
                    self.passive_size("SELL", probabilities, trend_direction, target_position),
                    self.sell_capacity,
                )
                if probabilities["trend"] >= probabilities["range"]:
                    quantity = min(quantity, max(1, position - target_position))
                self.add_sell(sell_quote, quantity)

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
