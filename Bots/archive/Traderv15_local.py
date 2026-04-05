from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math
import os


DEFAULT_EMERALDS_PARAMS = {
    "REFERENCE_PRICE": 10000.0,
    "REFERENCE_WEIGHT": 0.80,
    "MID_WEIGHT": 0.20,
    "MICRO_WEIGHT": 0.00,
    "INVENTORY_SKEW": 0.12,
    "BASE_TAKE_EDGE": 1.00,
    "BASE_QUOTE_EDGE": 1.75,
    "MAX_QUOTE_EDGE": 4.0,
    "MAX_TAKE_SIZE": 10,
    "PASSIVE_SIZE": 7,
    "SOFT_LIMIT_RATIO": 0.45,
}


DEFAULT_TOMATOES_PARAMS = {
    "MID_WEIGHT": 0.35,
    "MICRO_WEIGHT": 0.35,
    "HISTORY_WEIGHT": 0.30,
    "MOMENTUM_WEIGHT": 0.30,
    "IMBALANCE_WEIGHT": 0.70,
    "INVENTORY_SKEW": 0.06,
    "BASE_TAKE_EDGE": 1.50,
    "BASE_QUOTE_EDGE": 2.25,
    "MAX_QUOTE_EDGE": 5.0,
    "PASSIVE_SIZE": 8,
    "MAX_TAKE_SIZE": 8,
    "TREND_THRESHOLD": 1.25,
    "TREND_IMBALANCE_THRESHOLD": 0.15,
    "TOXIC_SPREAD_THRESHOLD": 15.0,
    "TOXIC_MOMENTUM_THRESHOLD": 1.5,
    "STRONG_TREND_THRESHOLD": 4.0,
    "SOFT_LIMIT_RATIO": 0.55,
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

    def classify_state(self) -> str:
        if float(self.spread) >= self.TOXIC_SPREAD_THRESHOLD and abs(self.momentum) < self.TOXIC_MOMENTUM_THRESHOLD:
            return "toxic"
        if (
            self.momentum >= self.TREND_THRESHOLD
            and self.imbalance >= self.TREND_IMBALANCE_THRESHOLD
            and float(self.micro) >= float(self.mid)
        ):
            return "trend_up"
        if (
            self.momentum <= -self.TREND_THRESHOLD
            and self.imbalance <= -self.TREND_IMBALANCE_THRESHOLD
            and float(self.micro) <= float(self.mid)
        ):
            return "trend_down"
        return "mean_revert"

    def target_band(self, regime: str) -> Tuple[int, int]:
        if regime == "trend_up":
            return (20, 36) if self.momentum >= self.STRONG_TREND_THRESHOLD else (10, 26)
        if regime == "trend_down":
            return (-36, -20) if self.momentum <= -self.STRONG_TREND_THRESHOLD else (-26, -10)
        if regime == "toxic":
            return -8, 8
        return -10, 10

    def target_position(self, regime: str) -> int:
        lower, upper = self.target_band(regime)
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

    def toxicity(self) -> float:
        score = 0.0
        if abs(self.momentum) >= 2.0:
            score += 0.5
        if abs(self.imbalance) >= 0.45:
            score += 0.5
        return score

    def fair_value(self, target_position: int) -> float:
        fair = (
            self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
            + self.HISTORY_WEIGHT * float(self.recent_average)
            + self.MOMENTUM_WEIGHT * self.momentum
            + self.IMBALANCE_WEIGHT * self.imbalance
        )
        fair += (target_position - self.projected_position()) / 18.0
        return fair

    def adjusted_fair_value(self, target_position: int) -> float:
        return self.fair_value(target_position) - (self.projected_position() * self.INVENTORY_SKEW)

    def take_edge(self, side: str, regime: str) -> float:
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

        if regime == "trend_up":
            edge += -0.4 if side == "BUY" else 0.6
        elif regime == "trend_down":
            edge += -0.4 if side == "SELL" else 0.6
        elif regime == "toxic":
            edge += 0.5
        else:
            if side == "BUY" and self.momentum <= -2.0:
                edge += 0.5
            if side == "SELL" and self.momentum >= 2.0:
                edge += 0.5

        return max(0.5, edge)

    def quote_edge(self, regime: str) -> float:
        edge = max(self.BASE_QUOTE_EDGE, float(self.spread) / 3.5)
        edge = min(self.MAX_QUOTE_EDGE, edge)

        if abs(self.projected_position()) >= self.soft_limit:
            edge += 0.5

        if regime == "toxic":
            edge += 1.0
        elif regime in {"trend_up", "trend_down"}:
            edge += 0.25

        edge += 0.35 * self.toxicity()
        return min(self.MAX_QUOTE_EDGE, edge)

    def passive_quotes(
        self,
        adjusted_fair: float,
        regime: str,
        target_position: int,
    ) -> Tuple[Optional[int], Optional[int]]:
        buy_quote = math.floor(adjusted_fair - self.quote_edge(regime))
        sell_quote = math.ceil(adjusted_fair + self.quote_edge(regime))
        buy_quote, sell_quote = self.clamp_inside_spread(buy_quote, sell_quote)

        position = self.projected_position()
        if regime == "trend_up":
            if buy_quote is not None and position < target_position:
                buy_quote = min(int(self.best_ask) - 1, max(int(self.best_bid) + 1, buy_quote + 1))
            if position <= 16:
                sell_quote = None
        elif regime == "trend_down":
            if sell_quote is not None and position > target_position:
                sell_quote = max(int(self.best_bid) + 1, min(int(self.best_ask) - 1, sell_quote - 1))
            if position >= -16:
                buy_quote = None
        elif regime == "toxic" and abs(position) <= 6:
            buy_quote = None
            sell_quote = None

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def passive_size(self, side: str, regime: str) -> int:
        size = self.PASSIVE_SIZE
        if int(self.spread) >= 14:
            size += 1

        if regime == "toxic":
            size = max(1, size - 3)
        elif regime in {"trend_up", "trend_down"}:
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

        return size

    def allow_passive(self, side: str, regime: str) -> bool:
        position = self.projected_position()
        if side == "BUY" and position >= self.soft_limit:
            return False
        if side == "SELL" and position <= -self.soft_limit:
            return False
        if regime == "toxic" and abs(position) <= 6:
            return False
        return True

    def take_orders(self, regime: str, target_position: int, adjusted_fair: float) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        if int(self.best_ask) <= adjusted_fair - self.take_edge("BUY", regime) and self.buy_capacity > 0:
            take_limit = self.MAX_TAKE_SIZE + (2 if regime == "trend_up" else 0)
            if regime != "mean_revert" and self.projected_position() >= target_position:
                pass
            else:
                quantity = min(self.best_ask_volume, take_limit)
                if regime != "mean_revert":
                    quantity = min(quantity, max(1, target_position - self.projected_position()))
                before = self.buy_capacity
                self.add_buy(int(self.best_ask), quantity)
                took_buy = self.buy_capacity < before

        if int(self.best_bid) >= adjusted_fair + self.take_edge("SELL", regime) and self.sell_capacity > 0:
            take_limit = self.MAX_TAKE_SIZE + (2 if regime == "trend_down" else 0)
            if regime != "mean_revert" and self.projected_position() <= target_position:
                pass
            else:
                quantity = min(self.best_bid_volume, take_limit)
                if regime != "mean_revert":
                    quantity = min(quantity, max(1, self.projected_position() - target_position))
                before = self.sell_capacity
                self.add_sell(int(self.best_bid), quantity)
                took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        regime = self.classify_state()
        target_position = self.target_position(regime)
        adjusted_fair = self.adjusted_fair_value(target_position)
        took_buy, took_sell = self.take_orders(regime, target_position, adjusted_fair)

        buy_quote, sell_quote = self.passive_quotes(adjusted_fair, regime, target_position)
        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.allow_passive("BUY", regime)
        ):
            if regime == "mean_revert" or position < target_position:
                quantity = min(self.passive_size("BUY", regime), self.buy_capacity)
                if regime != "mean_revert":
                    quantity = min(quantity, max(1, target_position - position))
                self.add_buy(buy_quote, quantity)

        position = self.projected_position()
        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.allow_passive("SELL", regime)
        ):
            if regime == "mean_revert" or position > target_position:
                quantity = min(self.passive_size("SELL", regime), self.sell_capacity)
                if regime != "mean_revert":
                    quantity = min(quantity, max(1, position - target_position))
                self.add_sell(sell_quote, quantity)

        return self.orders


class Trader:
    PARAMETER_ENV_VAR = "TRADER_PARAM_OVERRIDES"
    POSITION_LIMITS: Dict[str, int] = {
        "EMERALDS": 80,
        "TOMATOES": 80,
    }

    PRODUCT_TRADERS = {
        "EMERALDS": EmeraldsTrader,
        "TOMATOES": TomatoesTrader,
    }

    PRODUCT_DEFAULTS = {
        "EMERALDS": DEFAULT_EMERALDS_PARAMS,
        "TOMATOES": DEFAULT_TOMATOES_PARAMS,
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

    def load_parameter_overrides(self) -> Dict[str, Dict[str, float]]:
        raw = os.environ.get(self.PARAMETER_ENV_VAR, "")
        if not raw:
            return {}

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}

        if not isinstance(parsed, dict):
            return {}

        cleaned: Dict[str, Dict[str, float]] = {}
        for product, values in parsed.items():
            if product not in self.PRODUCT_DEFAULTS or not isinstance(values, dict):
                continue

            product_defaults = self.PRODUCT_DEFAULTS[product]
            cleaned[product] = {}
            for key, value in values.items():
                if key in product_defaults and isinstance(value, (int, float)):
                    cleaned[product][key] = float(value)

        return cleaned

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        mid_history = self.load_trader_data(state.traderData)
        parameter_overrides = self.load_parameter_overrides()

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
                parameter_overrides.get(product, {}),
            )
            result[product] = trader.run()

        conversions = 0
        trader_data = self.build_trader_data(mid_history)
        return result, conversions, trader_data
