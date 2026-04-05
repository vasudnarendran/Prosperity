from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json


EMERALDS_PARAMS = {
    "REFERENCE_PRICE": 10000.0,
    "REFERENCE_WEIGHT": 0.85,
    "MID_WEIGHT": 0.15,
    "INVENTORY_SKEW": 0.10,
    "TAKE_EDGE": 1.0,
    "QUOTE_EDGE": 2.0,
    "ORDER_SIZE": 10,
}

TOMATOES_PARAMS = {
    "MID_WEIGHT": 0.55,
    "MICRO_WEIGHT": 0.30,
    "TREND_WEIGHT": 0.15,
    "INVENTORY_SKEW": 0.05,
    "TAKE_EDGE": 1.5,
    "QUOTE_EDGE": 2.5,
    "ORDER_SIZE": 8,
    "MAX_HISTORY": 6,
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

        self.buy_levels: List[Tuple[int, int]] = []
        self.sell_levels: List[Tuple[int, int]] = []

        self.best_bid: Optional[int] = None
        self.best_ask: Optional[int] = None
        self.best_bid_volume = 0
        self.best_ask_volume = 0

        self.mid: Optional[float] = None
        self.micro: Optional[float] = None
        self.spread: Optional[int] = None

        self._load_market_state()

    def _load_market_state(self) -> None:
        if self.order_depth is None:
            return

        self.buy_levels = sorted(
            self.order_depth.buy_orders.items(),
            key=lambda x: x[0],
            reverse=True,
        )
        self.sell_levels = sorted(
            ((price, -volume) for price, volume in self.order_depth.sell_orders.items()),
            key=lambda x: x[0],
        )

        if not self.buy_levels or not self.sell_levels:
            return

        self.best_bid, self.best_bid_volume = self.buy_levels[0]
        self.best_ask, self.best_ask_volume = self.sell_levels[0]
        self.mid = (self.best_bid + self.best_ask) / 2
        self.spread = self.best_ask - self.best_bid

        total_top = self.best_bid_volume + self.best_ask_volume
        if total_top > 0:
            self.micro = (
                self.best_bid * self.best_ask_volume
                + self.best_ask * self.best_bid_volume
            ) / total_top
        else:
            self.micro = self.mid

        history = self.mid_history.get(self.product, [])
        history.append(self.mid)
        self.mid_history[self.product] = history[-self.HISTORY_LENGTH :]

    def has_book(self) -> bool:
        return self.best_bid is not None and self.best_ask is not None and self.mid is not None and self.micro is not None

    def projected_position(self) -> int:
        return self.position + sum(order.quantity for order in self.orders)

    def add_buy(self, price: int, quantity: int) -> None:
        quantity = min(int(quantity), self.buy_capacity)
        if quantity <= 0:
            return
        self.orders.append(Order(self.product, int(price), quantity))
        self.buy_capacity -= quantity

    def add_sell(self, price: int, quantity: int) -> None:
        quantity = min(int(quantity), self.sell_capacity)
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

        final_buy = None
        if buy_quote is not None:
            candidate = max(int(buy_quote), int(self.best_bid) + 1)
            if candidate < int(self.best_ask):
                final_buy = candidate

        final_sell = None
        if sell_quote is not None:
            candidate = min(int(sell_quote), int(self.best_ask) - 1)
            if candidate > int(self.best_bid):
                final_sell = candidate

        return final_buy, final_sell

    def run(self) -> List[Order]:
        return self.orders


class EmeraldsTrader(BaseProductTrader):
    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit)
        for key, value in EMERALDS_PARAMS.items():
            setattr(self, key, value)

    def fair_value(self) -> float:
        return (
            self.REFERENCE_WEIGHT * self.REFERENCE_PRICE
            + self.MID_WEIGHT * float(self.mid)
        )

    def adjusted_fair_value(self) -> float:
        return self.fair_value() - self.projected_position() * self.INVENTORY_SKEW

    def take_orders(self, fair: float) -> None:
        if self.best_ask is not None and self.best_ask <= fair - self.TAKE_EDGE:
            qty = min(self.ORDER_SIZE, self.best_ask_volume, self.buy_capacity)
            self.add_buy(self.best_ask, qty)

        if self.best_bid is not None and self.best_bid >= fair + self.TAKE_EDGE:
            qty = min(self.ORDER_SIZE, self.best_bid_volume, self.sell_capacity)
            self.add_sell(self.best_bid, qty)

    def passive_quotes(self, fair: float) -> Tuple[Optional[int], Optional[int]]:
        buy_quote = round(fair - self.QUOTE_EDGE)
        sell_quote = round(fair + self.QUOTE_EDGE)

        pos = self.projected_position()
        if pos > 20:
            buy_quote -= 1
            sell_quote -= 1
        elif pos < -20:
            buy_quote += 1
            sell_quote += 1

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        fair = self.adjusted_fair_value()
        self.take_orders(fair)

        buy_quote, sell_quote = self.passive_quotes(fair)

        if buy_quote is not None and self.buy_capacity > 0:
            self.add_buy(buy_quote, self.ORDER_SIZE)

        if sell_quote is not None and self.sell_capacity > 0:
            self.add_sell(sell_quote, self.ORDER_SIZE)

        return self.orders


class TomatoesTrader(BaseProductTrader):
    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit)
        for key, value in TOMATOES_PARAMS.items():
            setattr(self, key, value)

    def trend_signal(self) -> float:
        history = self.mid_history.get(self.product, [])
        history = history[-int(self.MAX_HISTORY):]

        if len(history) < 3:
            return 0.0

        short_avg = sum(history[-3:]) / 3
        long_avg = sum(history) / len(history)
        return short_avg - long_avg

    def fair_value(self) -> float:
        trend = self.trend_signal()
        fair = (
            self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
            + self.TREND_WEIGHT * (float(self.mid) + trend)
        )
        return fair

    def adjusted_fair_value(self) -> float:
        return self.fair_value() - self.projected_position() * self.INVENTORY_SKEW

    def take_orders(self, fair: float) -> None:
        if self.best_ask is not None and self.best_ask <= fair - self.TAKE_EDGE:
            qty = min(self.ORDER_SIZE, self.best_ask_volume, self.buy_capacity)
            self.add_buy(self.best_ask, qty)

        if self.best_bid is not None and self.best_bid >= fair + self.TAKE_EDGE:
            qty = min(self.ORDER_SIZE, self.best_bid_volume, self.sell_capacity)
            self.add_sell(self.best_bid, qty)

    def passive_quotes(self, fair: float) -> Tuple[Optional[int], Optional[int]]:
        edge = self.QUOTE_EDGE
        if self.spread is not None and self.spread >= 6:
            edge += 0.5

        buy_quote = round(fair - edge)
        sell_quote = round(fair + edge)

        pos = self.projected_position()
        if pos > 25:
            buy_quote -= 1
            sell_quote -= 1
        elif pos < -25:
            buy_quote += 1
            sell_quote += 1

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        fair = self.adjusted_fair_value()
        self.take_orders(fair)

        buy_quote, sell_quote = self.passive_quotes(fair)

        if buy_quote is not None and self.buy_capacity > 0:
            self.add_buy(buy_quote, self.ORDER_SIZE)

        if sell_quote is not None and self.sell_capacity > 0:
            self.add_sell(sell_quote, self.ORDER_SIZE)

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