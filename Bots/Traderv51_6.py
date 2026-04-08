from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


POSITION_LIMITS: Dict[str, int] = {
    "EMERALDS": 80,
    "TOMATOES": 80,
}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def ema(previous: Optional[float], current: float, alpha: float) -> float:
    if previous is None:
        return current
    return (1.0 - alpha) * previous + alpha * current


class Book:
    def __init__(self, order_depth: Optional[OrderDepth]) -> None:
        self.valid = False
        self.buy_levels: List[Tuple[int, int]] = []
        self.sell_levels: List[Tuple[int, int]] = []
        self.best_bid: Optional[int] = None
        self.best_ask: Optional[int] = None
        self.best_bid_volume = 0
        self.best_ask_volume = 0
        self.mid = 0.0
        self.spread = 0
        self.micro = 0.0
        self.imbalance = 0.0

        if order_depth is None:
            return

        self.buy_levels = sorted(
            ((int(price), int(volume)) for price, volume in order_depth.buy_orders.items()),
            key=lambda item: item[0],
            reverse=True,
        )
        self.sell_levels = sorted(
            ((int(price), abs(int(volume))) for price, volume in order_depth.sell_orders.items()),
            key=lambda item: item[0],
        )

        if not self.buy_levels or not self.sell_levels:
            return

        self.best_bid, self.best_bid_volume = self.buy_levels[0]
        self.best_ask, self.best_ask_volume = self.sell_levels[0]
        if self.best_bid >= self.best_ask:
            return

        self.mid = (self.best_bid + self.best_ask) / 2.0
        self.spread = self.best_ask - self.best_bid
        total_top = self.best_bid_volume + self.best_ask_volume
        if total_top > 0:
            self.micro = (
                self.best_ask * self.best_bid_volume + self.best_bid * self.best_ask_volume
            ) / total_top
            self.imbalance = (self.best_bid_volume - self.best_ask_volume) / total_top
        else:
            self.micro = self.mid
            self.imbalance = 0.0

        self.valid = True


class OrderManager:
    def __init__(self, product: str, position: int, limit: int) -> None:
        self.product = product
        self.position = int(position)
        self.limit = int(limit)
        self.buy_capacity = max(0, self.limit - self.position)
        self.sell_capacity = max(0, self.limit + self.position)
        self.orders: List[Order] = []

    def projected_position(self) -> int:
        return self.position + sum(order.quantity for order in self.orders)

    def add_buy(self, price: int, quantity: int) -> None:
        size = min(max(0, int(quantity)), self.buy_capacity)
        if size <= 0:
            return
        self.orders.append(Order(self.product, int(price), size))
        self.buy_capacity -= size

    def add_sell(self, price: int, quantity: int) -> None:
        size = min(max(0, int(quantity)), self.sell_capacity)
        if size <= 0:
            return
        self.orders.append(Order(self.product, int(price), -size))
        self.sell_capacity -= size


class EmeraldsBot:
    REFERENCE_PRICE = 10000.0
    MID_WEIGHT = 0.18
    INVENTORY_SKEW = 0.12
    BASE_QUOTE_SIZE = 10
    DEFAULT_EDGE = 7.0
    JOIN_EDGE = 2.0
    SOFT_LIMIT = 20
    TAKE_LEVELS = (
        (1.0, 6),
        (4.0, 12),
        (8.0, 20),
    )

    def __init__(self, state: TradingState) -> None:
        self.state = state
        self.product = "EMERALDS"
        self.book = Book(state.order_depths.get(self.product))
        self.manager = OrderManager(
            self.product,
            int(state.position.get(self.product, 0)),
            POSITION_LIMITS[self.product],
        )

    def fair_value(self) -> float:
        return (1.0 - self.MID_WEIGHT) * self.REFERENCE_PRICE + self.MID_WEIGHT * self.book.mid

    def reservation(self) -> float:
        return self.fair_value() - self.manager.projected_position() * self.INVENTORY_SKEW

    def take_size(self, edge: float) -> int:
        size = 0
        for distance, clip in self.TAKE_LEVELS:
            if edge >= distance:
                size = clip
        return size

    def take_orders(self, reservation: float) -> None:
        if not self.book.valid:
            return

        buy_edge = reservation - float(self.book.best_ask)
        buy_size = self.take_size(buy_edge)
        if buy_size > 0 and self.manager.buy_capacity > 0:
            if self.manager.projected_position() >= self.SOFT_LIMIT:
                buy_size = max(0, buy_size - 4)
            self.manager.add_buy(self.book.best_ask, min(self.book.best_ask_volume, buy_size))

        sell_edge = float(self.book.best_bid) - reservation
        sell_size = self.take_size(sell_edge)
        if sell_size > 0 and self.manager.sell_capacity > 0:
            if self.manager.projected_position() <= -self.SOFT_LIMIT:
                sell_size = max(0, sell_size - 4)
            self.manager.add_sell(self.book.best_bid, min(self.book.best_bid_volume, sell_size))

    def clear_inventory(self, reservation: float) -> None:
        if not self.book.valid:
            return

        position = self.manager.projected_position()
        if position > 0 and self.book.best_bid >= math.ceil(reservation):
            size = min(position, self.book.best_bid_volume, self.BASE_QUOTE_SIZE)
            self.manager.add_sell(self.book.best_bid, size)

        position = self.manager.projected_position()
        if position < 0 and self.book.best_ask <= math.floor(reservation):
            size = min(abs(position), self.book.best_ask_volume, self.BASE_QUOTE_SIZE)
            self.manager.add_buy(self.book.best_ask, size)

    def passive_quotes(self, reservation: float) -> Tuple[Optional[int], Optional[int]]:
        if not self.book.valid:
            return None, None

        buy_quote = int(round(reservation - self.DEFAULT_EDGE))
        sell_quote = int(round(reservation + self.DEFAULT_EDGE))

        for price, _volume in self.book.buy_levels[:2]:
            if price < reservation - self.DEFAULT_EDGE:
                buy_quote = price if reservation - price <= self.JOIN_EDGE else price + 1
                break

        for price, _volume in self.book.sell_levels[:2]:
            if price > reservation + self.DEFAULT_EDGE:
                sell_quote = price if price - reservation <= self.JOIN_EDGE else price - 1
                break

        position = self.manager.projected_position()
        if position >= self.SOFT_LIMIT:
            buy_quote -= 1
            sell_quote -= 1
        elif position <= -self.SOFT_LIMIT:
            buy_quote += 1
            sell_quote += 1

        if self.book.spread > 2:
            buy_quote = max(buy_quote, self.book.best_bid + 1)
            sell_quote = min(sell_quote, self.book.best_ask - 1)

        if buy_quote >= self.book.best_ask:
            buy_quote = self.book.best_bid
        if sell_quote <= self.book.best_bid:
            sell_quote = self.book.best_ask

        if buy_quote >= sell_quote:
            return self.book.best_bid, self.book.best_ask
        return buy_quote, sell_quote

    def passive_size(self, side: str) -> int:
        size = self.BASE_QUOTE_SIZE
        position = self.manager.projected_position()
        if side == "BUY":
            if position <= -self.SOFT_LIMIT:
                size += 4
            elif position >= self.SOFT_LIMIT:
                size = max(1, size - 6)
        else:
            if position >= self.SOFT_LIMIT:
                size += 4
            elif position <= -self.SOFT_LIMIT:
                size = max(1, size - 6)
        return size

    def run(self) -> List[Order]:
        if not self.book.valid:
            return []

        reservation = self.reservation()
        self.take_orders(reservation)
        self.clear_inventory(reservation)
        buy_quote, sell_quote = self.passive_quotes(self.reservation())

        if buy_quote is not None and self.manager.buy_capacity > 0:
            if self.manager.projected_position() < self.SOFT_LIMIT + self.BASE_QUOTE_SIZE:
                self.manager.add_buy(buy_quote, self.passive_size("BUY"))

        if sell_quote is not None and self.manager.sell_capacity > 0:
            if self.manager.projected_position() > -(self.SOFT_LIMIT + self.BASE_QUOTE_SIZE):
                self.manager.add_sell(sell_quote, self.passive_size("SELL"))

        return self.manager.orders


class TomatoesBot:
    WALL_EMA_ALPHA = 0.22
    WALL_STRENGTH_ALPHA = 0.22
    VOL_EMA_ALPHA = 0.22
    FLOW_EMA_ALPHA = 0.28

    HISTORY_LENGTH = 30
    REGRESSION_WINDOW = 12
    REGRESSION_HORIZON = 1

    ALPHA_REFERENCE_WEIGHT = 0.48
    ALPHA_MID_WEIGHT = 0.20
    ALPHA_MICRO_WEIGHT = 0.22
    ALPHA_FLOW_WEIGHT = 0.10
    ALPHA_CAP = 2.2
    ALPHA_BLEND_WEIGHT = 0.2667628572
    RANGE_ALPHA_DAMP = 0.65
    CONFLICT_ALPHA_DAMP = 0.72
    MOMENTUM_ALPHA_DAMP = 0.82
    POSITION_ALPHA_DAMP_START = 18
    POSITION_ALPHA_DAMP_END = 40

    FAIR_WALL_WEIGHT = 0.44
    FAIR_MID_WEIGHT = 0.18
    FAIR_MICRO_WEIGHT = 0.20
    FAIR_FLOW_WEIGHT = 0.08
    FAIR_REGRESSION_WEIGHT = 0.10
    FAIR_ALPHA_WEIGHT = 0.3325609293
    POSITION_BIAS_DIVISOR = 16.0
    RANGE_REVERT_WEIGHT = 0.18
    TREND_BONUS_WEIGHT = 0.10

    INVENTORY_SKEW = 0.0451458697
    BASE_QUOTE_EDGE = 2.0660764381
    BASE_TAKE_EDGE = 0.8322715145
    MAX_TAKE_SIZE = 10
    PASSIVE_SIZE = 9
    SOFT_LIMIT = 26

    TREND_EDGE_THRESHOLD = 0.9566826427
    STRONG_TREND_EDGE = 1.70
    FIT_THRESHOLD = 0.4237696448
    TOXIC_SPREAD = 12
    TOXIC_VOL = 2.8
    WALL_PERSISTENCE_FLOOR = 0.22

    def __init__(self, state: TradingState, memory: Dict[str, object]) -> None:
        self.state = state
        self.product = "TOMATOES"
        self.book = Book(state.order_depths.get(self.product))
        self.manager = OrderManager(
            self.product,
            int(state.position.get(self.product, 0)),
            POSITION_LIMITS[self.product],
        )
        self.memory = memory
        self.product_state = self.load_product_state()

    def load_product_state(self) -> Dict[str, object]:
        raw = self.memory.get("tomatoes", {})
        if not isinstance(raw, dict):
            raw = {}
        history_raw = raw.get("mid_history", [])
        history = []
        if isinstance(history_raw, list):
            history = [float(value) for value in history_raw[-self.HISTORY_LENGTH :]]
        return {
            "wall_fair_ema": float(raw.get("wall_fair_ema", 0.0)),
            "wall_strength_ema": float(raw.get("wall_strength_ema", 0.0)),
            "vol_ema": float(raw.get("vol_ema", 1.5)),
            "flow_ema": float(raw.get("flow_ema", 0.0)),
            "last_mid": float(raw.get("last_mid", 0.0)),
            "mid_history": history,
            "initialized": 1.0 if raw.get("initialized") else 0.0,
        }

    def save_product_state(self) -> None:
        self.memory["tomatoes"] = {
            "wall_fair_ema": float(self.product_state["wall_fair_ema"]),
            "wall_strength_ema": float(self.product_state["wall_strength_ema"]),
            "vol_ema": float(self.product_state["vol_ema"]),
            "flow_ema": float(self.product_state["flow_ema"]),
            "last_mid": float(self.product_state["last_mid"]),
            "mid_history": list(self.product_state["mid_history"])[-self.HISTORY_LENGTH :],
            "initialized": 1,
        }

    def current_wall_fair(self) -> Tuple[float, float]:
        bid_levels = self.book.buy_levels[:3]
        ask_levels = self.book.sell_levels[:3]
        if not bid_levels or not ask_levels:
            return self.book.mid, 0.0

        bid_weight = 0.0
        bid_price_sum = 0.0
        ask_weight = 0.0
        ask_price_sum = 0.0

        for index, (price, volume) in enumerate(bid_levels):
            effective = max(0.0, float(volume) - 2.0)
            if effective <= 0.0:
                continue
            weight = effective / (index + 1.0)
            bid_weight += weight
            bid_price_sum += weight * float(price)

        for index, (price, volume) in enumerate(ask_levels):
            effective = max(0.0, float(volume) - 2.0)
            if effective <= 0.0:
                continue
            weight = effective / (index + 1.0)
            ask_weight += weight
            ask_price_sum += weight * float(price)

        if bid_weight <= 1e-9 or ask_weight <= 1e-9:
            return self.book.mid, 0.0

        wall_bid = bid_price_sum / bid_weight
        wall_ask = ask_price_sum / ask_weight
        if wall_bid >= wall_ask:
            return self.book.mid, 0.0

        balance = min(bid_weight, ask_weight) / max(bid_weight, ask_weight)
        depth_strength = min(1.0, (bid_weight + ask_weight) / 18.0)
        strength = max(0.0, min(1.0, balance * depth_strength))
        return (wall_bid + wall_ask) / 2.0, strength

    def update_state(self) -> None:
        if not self.book.valid:
            return

        current_mid = self.book.mid
        current_wall, current_wall_strength = self.current_wall_fair()
        current_flow = self.book.imbalance * max(1.0, self.book.spread / 2.0)

        if self.product_state["initialized"] <= 0.0:
            self.product_state["wall_fair_ema"] = current_wall
            self.product_state["wall_strength_ema"] = current_wall_strength
            self.product_state["vol_ema"] = max(1.0, self.book.spread / 2.0)
            self.product_state["flow_ema"] = current_flow
            self.product_state["last_mid"] = current_mid
            self.product_state["mid_history"] = [current_mid]
            self.product_state["initialized"] = 1.0
            return

        ret = current_mid - float(self.product_state["last_mid"])
        self.product_state["wall_fair_ema"] = ema(
            float(self.product_state["wall_fair_ema"]), current_wall, self.WALL_EMA_ALPHA
        )
        self.product_state["wall_strength_ema"] = ema(
            float(self.product_state["wall_strength_ema"]), current_wall_strength, self.WALL_STRENGTH_ALPHA
        )
        self.product_state["vol_ema"] = ema(
            float(self.product_state["vol_ema"]), abs(ret), self.VOL_EMA_ALPHA
        )
        self.product_state["flow_ema"] = ema(
            float(self.product_state["flow_ema"]), current_flow, self.FLOW_EMA_ALPHA
        )
        history = list(self.product_state["mid_history"])
        history.append(current_mid)
        self.product_state["mid_history"] = history[-self.HISTORY_LENGTH :]
        self.product_state["last_mid"] = current_mid

    def recent_average(self) -> float:
        history = self.product_state["mid_history"]
        if not history:
            return self.book.mid
        return sum(history) / len(history)

    def momentum(self) -> float:
        history = self.product_state["mid_history"]
        if not history:
            return 0.0
        return self.book.mid - history[-1]

    def regression_metrics(self) -> Tuple[float, float, float, float]:
        history = list(self.product_state["mid_history"])[-self.REGRESSION_WINDOW :]
        if len(history) < 2:
            return self.book.mid, self.book.mid, 0.0, max(1.0, float(self.product_state["vol_ema"]))

        n = len(history)
        x_mean = (n - 1) / 2.0
        y_mean = sum(history) / n
        var_x = sum((index - x_mean) ** 2 for index in range(n))
        cov_xy = sum((index - x_mean) * (price - y_mean) for index, price in enumerate(history))
        slope = cov_xy / var_x if var_x else 0.0
        intercept = y_mean - slope * x_mean

        fitted = [intercept + slope * index for index in range(n)]
        predicted_now = fitted[-1]
        predicted_next = intercept + slope * ((n - 1) + self.REGRESSION_HORIZON)

        ss_tot = sum((price - y_mean) ** 2 for price in history)
        ss_res = sum((price - fit) ** 2 for price, fit in zip(history, fitted))
        fit_quality = 0.0 if ss_tot <= 1e-9 else clamp(1.0 - (ss_res / ss_tot), 0.0, 1.0)

        diffs = [abs(history[index] - history[index - 1]) for index in range(1, n)]
        volatility = sum(diffs) / len(diffs) if diffs else max(1.0, float(self.product_state["vol_ema"]))
        return predicted_now, predicted_next, fit_quality, max(1.0, volatility)

    def hybrid_alpha(self) -> float:
        reference_price = self.recent_average()
        wall_strength = clamp(float(self.product_state["wall_strength_ema"]), 0.0, 1.0)
        if wall_strength >= self.WALL_PERSISTENCE_FLOOR:
            reference_price += 0.20 * wall_strength * (float(self.product_state["wall_fair_ema"]) - reference_price)
        half_spread = max(1.0, float(self.book.spread) / 2.0)
        flow_fair = float(self.book.mid) + self.book.imbalance * half_spread
        hybrid_fair = (
            self.ALPHA_REFERENCE_WEIGHT * reference_price
            + self.ALPHA_MID_WEIGHT * float(self.book.mid)
            + self.ALPHA_MICRO_WEIGHT * float(self.book.micro)
            + self.ALPHA_FLOW_WEIGHT * flow_fair
        )
        return clamp(hybrid_fair - float(self.book.mid), -self.ALPHA_CAP, self.ALPHA_CAP)

    def guarded_alpha(self, hybrid_alpha: float, regression_edge: float, regime: str) -> float:
        weight = 1.0
        if regime in {"range", "stable"}:
            weight *= self.RANGE_ALPHA_DAMP
        if hybrid_alpha * regression_edge < 0:
            weight *= self.CONFLICT_ALPHA_DAMP
        if hybrid_alpha * self.book.imbalance < 0:
            weight *= self.CONFLICT_ALPHA_DAMP
        if hybrid_alpha * self.momentum() < 0:
            weight *= self.MOMENTUM_ALPHA_DAMP

        position = self.manager.projected_position()
        if hybrid_alpha * position > 0:
            abs_pos = abs(position)
            if abs_pos >= self.POSITION_ALPHA_DAMP_START:
                if abs_pos >= self.POSITION_ALPHA_DAMP_END:
                    weight = 0.0
                else:
                    span = self.POSITION_ALPHA_DAMP_END - self.POSITION_ALPHA_DAMP_START
                    ratio = (abs_pos - self.POSITION_ALPHA_DAMP_START) / max(1.0, span)
                    weight *= max(0.0, 1.0 - ratio)
        return hybrid_alpha * weight

    def classify_regime(self, predicted_edge: float, fit_quality: float, volatility: float) -> str:
        if self.book.spread >= self.TOXIC_SPREAD and volatility >= self.TOXIC_VOL:
            return "toxic"
        if (
            predicted_edge >= self.STRONG_TREND_EDGE
            and fit_quality >= self.FIT_THRESHOLD
            and self.book.imbalance > 0.03
            and self.book.micro >= self.book.mid
        ):
            return "strong_up"
        if (
            predicted_edge <= -self.STRONG_TREND_EDGE
            and fit_quality >= self.FIT_THRESHOLD
            and self.book.imbalance < -0.03
            and self.book.micro <= self.book.mid
        ):
            return "strong_down"
        if (
            predicted_edge >= self.TREND_EDGE_THRESHOLD
            and fit_quality >= self.FIT_THRESHOLD
            and self.book.imbalance >= 0.01
        ):
            return "trend_up"
        if (
            predicted_edge <= -self.TREND_EDGE_THRESHOLD
            and fit_quality >= self.FIT_THRESHOLD
            and self.book.imbalance <= -0.01
        ):
            return "trend_down"
        if self.book.spread <= 8 and volatility <= 1.8:
            return "stable"
        return "range"

    def target_position(self, regime: str, predicted_edge: float, fit_quality: float) -> int:
        conviction = clamp(
            abs(predicted_edge) * max(0.55, fit_quality) / max(1.0, self.book.spread / 2.0),
            0.0,
            1.0,
        )
        if regime == "strong_up":
            return int(round((self.SOFT_LIMIT + 10) * conviction))
        if regime == "strong_down":
            return -int(round((self.SOFT_LIMIT + 10) * conviction))
        if regime == "trend_up":
            return int(round((self.SOFT_LIMIT + 2) * conviction))
        if regime == "trend_down":
            return -int(round((self.SOFT_LIMIT + 2) * conviction))
        if regime == "toxic":
            return 0

        residual = self.book.mid - float(self.product_state["wall_fair_ema"])
        normalized = residual / max(2.0, float(self.product_state["vol_ema"]) * 2.0)
        return int(round(-0.22 * self.SOFT_LIMIT * clamp(normalized, -1.0, 1.0)))

    def fair_value(
        self,
        regime: str,
        target: int,
        predicted_now: float,
        predicted_next: float,
        guarded_alpha: float,
    ) -> float:
        half_spread = max(1.0, self.book.spread / 2.0)
        flow_fair = self.book.mid + self.book.imbalance * half_spread
        wall_strength = clamp(float(self.product_state["wall_strength_ema"]), 0.0, 1.0)
        wall_fair = float(self.product_state["wall_fair_ema"])

        fair = (
            self.FAIR_WALL_WEIGHT * wall_fair
            + self.FAIR_MID_WEIGHT * self.book.mid
            + self.FAIR_MICRO_WEIGHT * self.book.micro
            + self.FAIR_FLOW_WEIGHT * flow_fair
            + self.FAIR_REGRESSION_WEIGHT * predicted_next
        )
        fair += self.FAIR_ALPHA_WEIGHT * guarded_alpha
        fair += (target - self.manager.projected_position()) / self.POSITION_BIAS_DIVISOR

        line_gap = predicted_now - self.book.mid
        if regime in {"range", "stable"}:
            fair += self.RANGE_REVERT_WEIGHT * line_gap
        else:
            fair += self.TREND_BONUS_WEIGHT * (predicted_next - self.book.mid)

        if wall_strength < self.WALL_PERSISTENCE_FLOOR:
            fair -= 0.15 * (wall_fair - self.book.mid)
        return fair

    def reservation(self, fair: float, target: int) -> float:
        pressure = self.manager.projected_position() - target
        return fair - pressure * self.INVENTORY_SKEW

    def desired_buy_qty(self, target: int) -> int:
        return max(0, target - self.manager.projected_position())

    def desired_sell_qty(self, target: int) -> int:
        return max(0, self.manager.projected_position() - target)

    def take_threshold(
        self,
        side: str,
        regime: str,
        target: int,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
    ) -> float:
        threshold = self.BASE_TAKE_EDGE + 0.08 * min(3.0, volatility)
        position = self.manager.projected_position()

        if regime == "stable":
            threshold += 0.02
        elif regime == "range":
            threshold += 0.00
        elif regime == "trend_up":
            threshold += -0.28 if side == "BUY" else 0.42
        elif regime == "trend_down":
            threshold += -0.28 if side == "SELL" else 0.42
        elif regime == "strong_up":
            threshold += -0.40 if side == "BUY" else 0.60
        elif regime == "strong_down":
            threshold += -0.40 if side == "SELL" else 0.60
        else:
            threshold += 0.60

        if side == "BUY" and position < target:
            threshold -= 0.10
        if side == "SELL" and position > target:
            threshold -= 0.10

        if predicted_edge > 0 and side == "BUY":
            threshold -= min(0.16, 0.05 * predicted_edge * max(0.5, fit_quality))
        elif predicted_edge < 0 and side == "SELL":
            threshold -= min(0.16, 0.05 * abs(predicted_edge) * max(0.5, fit_quality))

        if regime in {"trend_up", "trend_down", "strong_up", "strong_down"} and fit_quality < 0.55:
            threshold += 0.10
        if regime in {"strong_up", "strong_down"} and fit_quality < 0.65:
            threshold += 0.10
        return max(0.25, threshold)

    def take_size(self, side: str, regime: str, target: int) -> int:
        desired = abs(target - self.manager.projected_position())
        size = min(self.MAX_TAKE_SIZE, max(2, desired))
        if regime in {"strong_up", "strong_down"}:
            size += 2
        if self.book.spread <= 8 and abs(self.manager.projected_position()) <= 8:
            size += 1
        if side == "BUY" and target < self.manager.projected_position():
            size = max(2, size - 3)
        if side == "SELL" and target > self.manager.projected_position():
            size = max(2, size - 3)
        return min(self.MAX_TAKE_SIZE, size)

    def clear_inventory(self, reservation: float, regime: str, target: int) -> None:
        position = self.manager.projected_position()
        long_clear = reservation
        short_clear = reservation
        if regime in {"trend_up", "strong_up"} and position > max(0, target):
            long_clear += 1.0
        if regime in {"trend_down", "strong_down"} and position < min(0, target):
            short_clear -= 1.0

        if position > 0 and self.book.best_bid >= math.floor(long_clear):
            size = min(position, self.book.best_bid_volume, self.PASSIVE_SIZE)
            self.manager.add_sell(self.book.best_bid, size)

        position = self.manager.projected_position()
        if position < 0 and self.book.best_ask <= math.ceil(short_clear):
            size = min(abs(position), self.book.best_ask_volume, self.PASSIVE_SIZE)
            self.manager.add_buy(self.book.best_ask, size)

    def take_orders(
        self,
        reservation: float,
        regime: str,
        target: int,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
    ) -> None:
        buy_threshold = self.take_threshold("BUY", regime, target, predicted_edge, fit_quality, volatility)
        sell_threshold = self.take_threshold("SELL", regime, target, predicted_edge, fit_quality, volatility)

        for price, volume in self.book.sell_levels[:2]:
            if self.manager.buy_capacity <= 0:
                break
            if regime != "range" and self.manager.projected_position() >= target:
                break
            edge = reservation - float(price)
            if edge < buy_threshold:
                break
            size = min(volume, self.manager.buy_capacity, self.take_size("BUY", regime, target))
            if regime != "range":
                desired = self.desired_buy_qty(target)
                if desired <= 0:
                    continue
                size = min(size, desired)
            if size > 0:
                self.manager.add_buy(price, size)

        for price, volume in self.book.buy_levels[:2]:
            if self.manager.sell_capacity <= 0:
                break
            if regime != "range" and self.manager.projected_position() <= target:
                break
            edge = float(price) - reservation
            if edge < sell_threshold:
                break
            size = min(volume, self.manager.sell_capacity, self.take_size("SELL", regime, target))
            if regime != "range":
                desired = self.desired_sell_qty(target)
                if desired <= 0:
                    continue
                size = min(size, desired)
            if size > 0:
                self.manager.add_sell(price, size)

    def quote_edge(self, side: str, regime: str, target: int, volatility: float, fit_quality: float) -> float:
        edge = self.BASE_QUOTE_EDGE + 0.18 * min(4.0, volatility)
        edge += 0.08 * max(0, self.book.spread - 6)
        pressure = self.manager.projected_position() - target

        if regime == "stable":
            edge -= 0.35
        elif regime == "range":
            edge += 0.00
        elif regime in {"trend_up", "trend_down"}:
            edge += 0.16 + 0.10 * fit_quality
        elif regime in {"strong_up", "strong_down"}:
            edge += 0.16 + 0.08 * fit_quality
        else:
            edge += 0.80

        if side == "BUY":
            if pressure > 0:
                edge += 0.85 * clamp(pressure / self.SOFT_LIMIT, 0.0, 1.0)
            elif pressure < 0:
                edge -= 0.22 * clamp(abs(pressure) / self.SOFT_LIMIT, 0.0, 1.0)
        else:
            if pressure < 0:
                edge += 0.85 * clamp(abs(pressure) / self.SOFT_LIMIT, 0.0, 1.0)
            elif pressure > 0:
                edge -= 0.22 * clamp(pressure / self.SOFT_LIMIT, 0.0, 1.0)
        return max(1.2, edge)

    def passive_size(
        self,
        side: str,
        regime: str,
        target: int,
        volatility: float,
        fit_quality: float,
    ) -> int:
        size = self.PASSIVE_SIZE
        if regime == "stable":
            size += 1
        elif regime == "toxic":
            size = max(2, size - 3)

        pressure = self.manager.projected_position() - target
        if side == "BUY":
            if pressure < 0:
                size += 2
            elif pressure > 0:
                size = max(2, size - 3)
        else:
            if pressure > 0:
                size += 2
            elif pressure < 0:
                size = max(2, size - 3)
        if regime in {"trend_up", "trend_down"} and volatility <= 2.2:
            size += 1
        if fit_quality < 0.45:
            size = max(2, size - 1)
        if regime in {"strong_up", "strong_down"} and fit_quality < 0.55:
            size = max(2, size - 1)
        return size

    def allow_passive(self, side: str, regime: str, target: int) -> bool:
        position = self.manager.projected_position()
        if side == "BUY" and position >= POSITION_LIMITS[self.product]:
            return False
        if side == "SELL" and position <= -POSITION_LIMITS[self.product]:
            return False
        if regime == "toxic" and abs(position) <= 4:
            return False
        if regime in {"trend_up", "strong_up"} and side == "SELL" and position <= max(4, target // 4):
            return False
        if regime in {"trend_down", "strong_down"} and side == "BUY" and position >= min(-4, target // 4):
            return False
        return True

    def passive_quotes(
        self,
        reservation: float,
        regime: str,
        target: int,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
    ) -> Tuple[Optional[int], Optional[int]]:
        buy_edge = self.quote_edge("BUY", regime, target, volatility, fit_quality)
        sell_edge = self.quote_edge("SELL", regime, target, volatility, fit_quality)
        buy_quote = math.floor(reservation - buy_edge)
        sell_quote = math.ceil(reservation + sell_edge)

        if regime in {"trend_up", "strong_up"}:
            if buy_quote < self.book.best_bid + 1 and self.manager.projected_position() < target:
                buy_quote = self.book.best_bid + 1
            if predicted_edge >= self.TREND_EDGE_THRESHOLD and self.manager.projected_position() > 0:
                sell_quote += 1
        elif regime in {"trend_down", "strong_down"}:
            if sell_quote > self.book.best_ask - 1 and self.manager.projected_position() > target:
                sell_quote = self.book.best_ask - 1
            if predicted_edge <= -self.TREND_EDGE_THRESHOLD and self.manager.projected_position() < 0:
                buy_quote -= 1

        if buy_quote >= self.book.best_ask:
            buy_quote = self.book.best_bid
        if sell_quote <= self.book.best_bid:
            sell_quote = self.book.best_ask

        if buy_quote >= sell_quote:
            buy_quote = self.book.best_bid
            sell_quote = self.book.best_ask
        return buy_quote, sell_quote

    def run(self) -> Tuple[List[Order], Dict[str, object]]:
        if not self.book.valid:
            self.save_product_state()
            return [], self.memory

        self.update_state()
        predicted_now, predicted_next, fit_quality, volatility = self.regression_metrics()
        regression_edge = predicted_next - float(self.book.mid)
        provisional_regime = self.classify_regime(regression_edge, fit_quality, volatility)
        hybrid_alpha = self.hybrid_alpha()
        guarded_alpha = self.guarded_alpha(hybrid_alpha, regression_edge, provisional_regime)
        predicted_edge = (
            (1.0 - self.ALPHA_BLEND_WEIGHT) * regression_edge
            + self.ALPHA_BLEND_WEIGHT * guarded_alpha
        )
        regime = self.classify_regime(predicted_edge, fit_quality, volatility)
        target = self.target_position(regime, predicted_edge, fit_quality)
        fair = self.fair_value(regime, target, predicted_now, predicted_next, guarded_alpha)
        reservation = self.reservation(fair, target)

        self.take_orders(reservation, regime, target, predicted_edge, fit_quality, volatility)
        self.clear_inventory(self.reservation(fair, target), regime, target)
        reservation = self.reservation(fair, target)
        buy_quote, sell_quote = self.passive_quotes(
            reservation, regime, target, predicted_edge, fit_quality, volatility
        )

        if (
            buy_quote is not None
            and self.manager.buy_capacity > 0
            and self.allow_passive("BUY", regime, target)
        ):
            size = min(
                self.passive_size("BUY", regime, target, volatility, fit_quality),
                self.manager.buy_capacity,
            )
            if regime != "range":
                desired = self.desired_buy_qty(target)
                if desired <= 0:
                    size = 0
                else:
                    size = min(size, desired)
            if size > 0:
                self.manager.add_buy(buy_quote, size)

        if (
            sell_quote is not None
            and self.manager.sell_capacity > 0
            and self.allow_passive("SELL", regime, target)
        ):
            size = min(
                self.passive_size("SELL", regime, target, volatility, fit_quality),
                self.manager.sell_capacity,
            )
            if regime != "range":
                desired = self.desired_sell_qty(target)
                if desired <= 0:
                    size = 0
                else:
                    size = min(size, desired)
            if size > 0:
                self.manager.add_sell(sell_quote, size)

        self.save_product_state()
        return self.manager.orders, self.memory


class Trader:
    def load_memory(self, trader_data: str) -> Dict[str, object]:
        if not trader_data:
            return {}
        try:
            parsed = json.loads(trader_data)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def dump_memory(self, memory: Dict[str, object]) -> str:
        return json.dumps(memory, separators=(",", ":"))

    def run(self, state: TradingState):
        memory = self.load_memory(state.traderData)
        result: Dict[str, List[Order]] = {}

        emeralds = EmeraldsBot(state)
        result["EMERALDS"] = emeralds.run()

        tomatoes = TomatoesBot(state, memory)
        tomato_orders, updated_memory = tomatoes.run()
        result["TOMATOES"] = tomato_orders

        for product in state.order_depths:
            if product not in result:
                result[product] = []

        return result, 0, self.dump_memory(updated_memory)
