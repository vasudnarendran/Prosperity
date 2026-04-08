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
    WALL_EMA_ALPHA = 0.25
    MID_EMA_ALPHA = 0.18
    VOL_EMA_ALPHA = 0.22
    TREND_EMA_ALPHA = 0.28

    FAIR_WALL_WEIGHT = 0.55
    FAIR_MID_WEIGHT = 0.15
    FAIR_MICRO_WEIGHT = 0.20
    FAIR_FLOW_WEIGHT = 0.10

    INVENTORY_SKEW = 0.045
    BASE_QUOTE_EDGE = 2.2
    BASE_TAKE_EDGE = 0.9
    MAX_TAKE_SIZE = 10
    PASSIVE_SIZE = 8
    SOFT_LIMIT = 26

    TREND_SCORE = 0.70
    STRONG_SCORE = 1.50
    TOXIC_SPREAD = 12
    TOXIC_VOL = 2.8

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

    def load_product_state(self) -> Dict[str, float]:
        raw = self.memory.get("tomatoes", {})
        if not isinstance(raw, dict):
            raw = {}
        return {
            "wall_fair_ema": float(raw.get("wall_fair_ema", 0.0)),
            "mid_ema": float(raw.get("mid_ema", 0.0)),
            "vol_ema": float(raw.get("vol_ema", 1.5)),
            "trend_ema": float(raw.get("trend_ema", 0.0)),
            "last_mid": float(raw.get("last_mid", 0.0)),
            "initialized": 1.0 if raw.get("initialized") else 0.0,
        }

    def save_product_state(self) -> None:
        self.memory["tomatoes"] = {
            "wall_fair_ema": self.product_state["wall_fair_ema"],
            "mid_ema": self.product_state["mid_ema"],
            "vol_ema": self.product_state["vol_ema"],
            "trend_ema": self.product_state["trend_ema"],
            "last_mid": self.product_state["last_mid"],
            "initialized": 1,
        }

    def wall_price(self, levels: List[Tuple[int, int]]) -> Optional[float]:
        if not levels:
            return None
        top = levels[:3]
        max_volume = max(volume for _, volume in top)
        strong = [(price, volume) for price, volume in top if volume >= 0.60 * max_volume]
        total = sum(volume for _, volume in strong)
        if total <= 0:
            return None
        return sum(price * volume for price, volume in strong) / total

    def current_wall_fair(self) -> float:
        wall_bid = self.wall_price(self.book.buy_levels)
        wall_ask = self.wall_price(self.book.sell_levels)
        if wall_bid is not None and wall_ask is not None and wall_bid < wall_ask:
            return (wall_bid + wall_ask) / 2.0
        return self.book.mid

    def update_state(self) -> None:
        if not self.book.valid:
            return

        current_mid = self.book.mid
        current_wall = self.current_wall_fair()
        current_flow = self.book.imbalance * max(1.0, self.book.spread / 2.0)

        if self.product_state["initialized"] <= 0.0:
            self.product_state["wall_fair_ema"] = current_wall
            self.product_state["mid_ema"] = current_mid
            self.product_state["vol_ema"] = max(1.0, self.book.spread / 2.0)
            self.product_state["trend_ema"] = current_flow
            self.product_state["last_mid"] = current_mid
            self.product_state["initialized"] = 1.0
            return

        ret = current_mid - self.product_state["last_mid"]
        self.product_state["wall_fair_ema"] = ema(
            self.product_state["wall_fair_ema"], current_wall, self.WALL_EMA_ALPHA
        )
        self.product_state["mid_ema"] = ema(
            self.product_state["mid_ema"], current_mid, self.MID_EMA_ALPHA
        )
        self.product_state["vol_ema"] = ema(
            self.product_state["vol_ema"], abs(ret), self.VOL_EMA_ALPHA
        )

        trend_raw = (
            self.product_state["wall_fair_ema"] - self.product_state["mid_ema"]
            + 0.60 * (self.book.micro - self.book.mid)
            + 0.80 * current_flow
        )
        self.product_state["trend_ema"] = ema(
            self.product_state["trend_ema"], trend_raw, self.TREND_EMA_ALPHA
        )
        self.product_state["last_mid"] = current_mid

    def fair_value(self) -> float:
        half_spread = max(1.0, self.book.spread / 2.0)
        flow_fair = self.book.mid + self.book.imbalance * half_spread
        fair = (
            self.FAIR_WALL_WEIGHT * self.product_state["wall_fair_ema"]
            + self.FAIR_MID_WEIGHT * self.book.mid
            + self.FAIR_MICRO_WEIGHT * self.book.micro
            + self.FAIR_FLOW_WEIGHT * flow_fair
        )

        trend = self.product_state["trend_ema"]
        if trend > self.TREND_SCORE:
            fair += 0.20 * min(2.0, trend)
        elif trend < -self.TREND_SCORE:
            fair -= 0.20 * min(2.0, abs(trend))
        return fair

    def regime(self) -> str:
        trend = self.product_state["trend_ema"]
        vol = self.product_state["vol_ema"]
        if self.book.spread >= self.TOXIC_SPREAD and vol >= self.TOXIC_VOL:
            return "toxic"
        if trend >= self.STRONG_SCORE and self.book.imbalance > 0.03:
            return "strong_up"
        if trend <= -self.STRONG_SCORE and self.book.imbalance < -0.03:
            return "strong_down"
        if trend >= self.TREND_SCORE:
            return "trend_up"
        if trend <= -self.TREND_SCORE:
            return "trend_down"
        if self.book.spread <= 8 and vol <= 1.8:
            return "stable"
        return "range"

    def target_position(self, regime: str, fair: float) -> int:
        alpha = fair - self.book.mid
        conviction = clamp(abs(alpha) / max(1.0, self.book.spread / 2.0), 0.0, 1.0)
        if regime == "strong_up":
            return int(round((self.SOFT_LIMIT + 8) * conviction))
        if regime == "strong_down":
            return -int(round((self.SOFT_LIMIT + 8) * conviction))
        if regime == "trend_up":
            return int(round(self.SOFT_LIMIT * conviction))
        if regime == "trend_down":
            return -int(round(self.SOFT_LIMIT * conviction))
        if regime == "toxic":
            return 0

        residual = self.book.mid - self.product_state["wall_fair_ema"]
        normalized = residual / max(2.0, self.product_state["vol_ema"] * 2.0)
        return int(round(-0.25 * self.SOFT_LIMIT * clamp(normalized, -1.0, 1.0)))

    def reservation(self, fair: float, target: int) -> float:
        pressure = self.manager.projected_position() - target
        return fair - pressure * self.INVENTORY_SKEW

    def desired_buy_qty(self, target: int) -> int:
        return max(0, target - self.manager.projected_position())

    def desired_sell_qty(self, target: int) -> int:
        return max(0, self.manager.projected_position() - target)

    def inventory_pressure(self, target: int) -> float:
        return clamp(
            abs(self.manager.projected_position() - target) / max(1.0, float(self.SOFT_LIMIT)),
            0.0,
            1.0,
        )

    def take_threshold(self, side: str, regime: str, target: int) -> float:
        threshold = self.BASE_TAKE_EDGE + 0.10 * min(3.0, self.product_state["vol_ema"])
        position = self.manager.projected_position()

        if regime == "stable":
            threshold += 0.05
        elif regime == "range":
            threshold += 0.00
        elif regime == "trend_up":
            threshold += -0.35 if side == "BUY" else 0.50
        elif regime == "trend_down":
            threshold += -0.35 if side == "SELL" else 0.50
        elif regime == "strong_up":
            threshold += -0.50 if side == "BUY" else 0.70
        elif regime == "strong_down":
            threshold += -0.50 if side == "SELL" else 0.70
        else:
            threshold += 0.65

        if side == "BUY" and position < target:
            threshold -= 0.10
        if side == "SELL" and position > target:
            threshold -= 0.10
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
        sell_clear = reservation
        buy_clear = reservation
        if regime in {"trend_up", "strong_up"} and position > target:
            sell_clear -= 1.0
        if regime in {"trend_down", "strong_down"} and position < target:
            buy_clear += 1.0

        if position > 0 and self.book.best_bid >= math.floor(sell_clear):
            size = min(position, self.book.best_bid_volume, self.PASSIVE_SIZE)
            self.manager.add_sell(self.book.best_bid, size)

        position = self.manager.projected_position()
        if position < 0 and self.book.best_ask <= math.ceil(buy_clear):
            size = min(abs(position), self.book.best_ask_volume, self.PASSIVE_SIZE)
            self.manager.add_buy(self.book.best_ask, size)

    def take_orders(self, reservation: float, regime: str, target: int) -> None:
        buy_threshold = self.take_threshold("BUY", regime, target)
        sell_threshold = self.take_threshold("SELL", regime, target)

        for price, volume in self.book.sell_levels[:2]:
            if self.manager.buy_capacity <= 0:
                break
            edge = reservation - float(price)
            if edge < buy_threshold:
                break
            size = min(volume, self.manager.buy_capacity, self.take_size("BUY", regime, target))
            if regime in {"trend_up", "strong_up"}:
                desired = self.desired_buy_qty(target)
                if desired <= 0:
                    continue
                size = min(size, desired)
            if size > 0:
                self.manager.add_buy(price, size)

        for price, volume in self.book.buy_levels[:2]:
            if self.manager.sell_capacity <= 0:
                break
            edge = float(price) - reservation
            if edge < sell_threshold:
                break
            size = min(volume, self.manager.sell_capacity, self.take_size("SELL", regime, target))
            if regime in {"trend_down", "strong_down"}:
                desired = self.desired_sell_qty(target)
                if desired <= 0:
                    continue
                size = min(size, desired)
            if size > 0:
                self.manager.add_sell(price, size)

    def quote_edge(self, side: str, regime: str, target: int) -> float:
        edge = self.BASE_QUOTE_EDGE + 0.20 * min(4.0, self.product_state["vol_ema"])
        edge += 0.08 * max(0, self.book.spread - 6)
        pressure = self.manager.projected_position() - target

        if regime == "stable":
            edge -= 0.40
        elif regime == "range":
            edge += 0.00
        elif regime in {"trend_up", "trend_down"}:
            edge += 0.15
        elif regime in {"strong_up", "strong_down"}:
            edge += 0.10
        else:
            edge += 0.85

        if side == "BUY":
            if pressure > 0:
                edge += 0.90 * clamp(pressure / self.SOFT_LIMIT, 0.0, 1.0)
            elif pressure < 0:
                edge -= 0.25 * clamp(abs(pressure) / self.SOFT_LIMIT, 0.0, 1.0)
        else:
            if pressure < 0:
                edge += 0.90 * clamp(abs(pressure) / self.SOFT_LIMIT, 0.0, 1.0)
            elif pressure > 0:
                edge -= 0.25 * clamp(pressure / self.SOFT_LIMIT, 0.0, 1.0)
        return max(1.2, edge)

    def passive_size(self, side: str, regime: str, target: int) -> int:
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
        return size

    def allow_passive(self, side: str, regime: str, target: int) -> bool:
        position = self.manager.projected_position()
        if side == "BUY" and position >= POSITION_LIMITS[self.product]:
            return False
        if side == "SELL" and position <= -POSITION_LIMITS[self.product]:
            return False
        if regime == "toxic" and abs(position) <= 4:
            return False
        if regime == "strong_up" and side == "SELL" and position <= max(4, target // 4):
            return False
        if regime == "trend_up" and side == "SELL" and position <= 4:
            return False
        if regime == "strong_down" and side == "BUY" and position >= min(-4, target // 4):
            return False
        if regime == "trend_down" and side == "BUY" and position >= -4:
            return False
        return True

    def passive_quotes(self, reservation: float, regime: str, target: int) -> Tuple[Optional[int], Optional[int]]:
        buy_edge = self.quote_edge("BUY", regime, target)
        sell_edge = self.quote_edge("SELL", regime, target)
        buy_quote = math.floor(reservation - buy_edge)
        sell_quote = math.ceil(reservation + sell_edge)

        position = self.manager.projected_position()
        if regime in {"trend_up", "strong_up"}:
            if position < target:
                buy_quote += 1
            elif position > target:
                sell_quote -= 1
        elif regime in {"trend_down", "strong_down"}:
            if position > target:
                sell_quote -= 1
            elif position < target:
                buy_quote += 1

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
        fair = self.fair_value()
        regime = self.regime()
        target = self.target_position(regime, fair)
        reservation = self.reservation(fair, target)

        self.take_orders(reservation, regime, target)
        self.clear_inventory(self.reservation(fair, target), regime, target)
        reservation = self.reservation(fair, target)
        buy_quote, sell_quote = self.passive_quotes(reservation, regime, target)

        if (
            buy_quote is not None
            and self.manager.buy_capacity > 0
            and self.allow_passive("BUY", regime, target)
        ):
            size = min(self.passive_size("BUY", regime, target), self.manager.buy_capacity)
            if regime in {"trend_up", "strong_up"}:
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
            size = min(self.passive_size("SELL", regime, target), self.manager.sell_capacity)
            if regime in {"trend_down", "strong_down"}:
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
