from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


DEFAULT_EMERALDS_PARAMS = {
    "REFERENCE_PRICE": 10000.0,
    "REFERENCE_WEIGHT": 0.80,
    "MID_WEIGHT": 0.20,
    "INVENTORY_SKEW": 0.12,
    "TAKE_EDGE": 4.0,
    "PASSIVE_EDGE": 8.0,
    "BASE_ORDER_SIZE": 10,
    "SOFT_LIMIT_RATIO": 0.25,
}


DEFAULT_TOMATOES_PARAMS = {
    "MID_WEIGHT": 0.55,
    "MICRO_WEIGHT": 0.45,
    "REGRESSION_WINDOW": 8,
    "REGRESSION_HORIZON": 2.0,
    "ALPHA_SCALE": 1.10,
    "FIT_THRESHOLD": 0.45,
    "TREND_EDGE_THRESHOLD": 1.00,
    "STRONG_TREND_EDGE": 2.50,
    "TREND_POSITION": 28,
    "STRONG_TREND_POSITION": 44,
    "INVENTORY_SKEW": 0.035,
    "POSITION_BIAS_DIVISOR": 12.0,
    "BASE_EDGE": 2.50,
    "MAX_EDGE": 5.0,
    "TAKE_EDGE_FRACTION": 0.55,
    "VOL_EDGE_COEF": 0.72,
    "INV_EDGE_COEF": 0.32,
    "TREND_EDGE_BONUS": 0.20,
    "VOLATILE_EDGE_BONUS": 1.00,
    "PASSIVE_SIZE": 8,
    "MAX_TAKE_SIZE": 10,
    "SOFT_LIMIT_RATIO": 0.65,
    "TOXIC_VOLATILITY_THRESHOLD": 3.2,
    "VOL_CONTROL_WINDOW": 8,
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
    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit)
        for key, value in DEFAULT_EMERALDS_PARAMS.items():
            setattr(self, key, value)
        self.soft_limit = int(position_limit * self.SOFT_LIMIT_RATIO)

    def fair_value(self) -> float:
        fair = (
            self.REFERENCE_WEIGHT * self.REFERENCE_PRICE
            + self.MID_WEIGHT * float(self.mid)
        )
        return fair - (self.projected_position() * self.INVENTORY_SKEW)

    def passive_size(self, side: str) -> int:
        size = int(self.BASE_ORDER_SIZE)
        position = self.projected_position()
        if side == "BUY":
            if position <= -self.soft_limit:
                size += 4
            elif position >= self.soft_limit:
                size = max(1, size - 4)
        else:
            if position >= self.soft_limit:
                size += 4
            elif position <= -self.soft_limit:
                size = max(1, size - 4)
        return size

    def take_orders(self, fair: float) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        if int(self.best_ask) <= fair - self.TAKE_EDGE and self.buy_capacity > 0:
            before = self.buy_capacity
            self.add_buy(int(self.best_ask), min(self.best_ask_volume, self.passive_size("BUY")))
            took_buy = self.buy_capacity < before

        if int(self.best_bid) >= fair + self.TAKE_EDGE and self.sell_capacity > 0:
            before = self.sell_capacity
            self.add_sell(int(self.best_bid), min(self.best_bid_volume, self.passive_size("SELL")))
            took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def passive_quotes(self, fair: float) -> Tuple[Optional[int], Optional[int]]:
        buy_quote = math.floor(fair - self.PASSIVE_EDGE)
        sell_quote = math.ceil(fair + self.PASSIVE_EDGE)

        position = self.projected_position()
        if position >= self.soft_limit:
            buy_quote -= 1
            sell_quote -= 1
        elif position <= -self.soft_limit:
            buy_quote += 1
            sell_quote += 1

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        fair = self.fair_value()
        took_buy, took_sell = self.take_orders(fair)
        buy_quote, sell_quote = self.passive_quotes(fair)
        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and position < self.soft_limit + int(self.BASE_ORDER_SIZE)
        ):
            self.add_buy(buy_quote, self.passive_size("BUY"))

        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and position > -(self.soft_limit + int(self.BASE_ORDER_SIZE))
        ):
            self.add_sell(sell_quote, self.passive_size("SELL"))

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
        for key, value in DEFAULT_TOMATOES_PARAMS.items():
            setattr(self, key, value)
        self.soft_limit = int(position_limit * self.SOFT_LIMIT_RATIO)

    def regression_alpha(self) -> Tuple[float, float, float]:
        history = self.mid_history.get(self.product, [])
        window = history[-int(self.REGRESSION_WINDOW) :]
        if len(window) < 2:
            return 0.0, 0.0, 0.0

        n = len(window)
        x_mean = (n - 1) / 2.0
        y_mean = sum(window) / n
        var_x = sum((index - x_mean) ** 2 for index in range(n))
        cov_xy = sum((index - x_mean) * (price - y_mean) for index, price in enumerate(window))
        slope = cov_xy / var_x if var_x else 0.0
        intercept = y_mean - slope * x_mean

        fitted = [intercept + slope * index for index in range(n)]
        predicted_next = intercept + slope * ((n - 1) + self.REGRESSION_HORIZON)

        ss_tot = sum((price - y_mean) ** 2 for price in window)
        ss_res = sum((price - fit) ** 2 for price, fit in zip(window, fitted))
        fit_quality = 0.0 if ss_tot <= 1e-9 else max(0.0, min(1.0, 1.0 - (ss_res / ss_tot)))

        diffs = [abs(window[index] - window[index - 1]) for index in range(1, n)]
        volatility = sum(diffs) / len(diffs) if diffs else 0.0
        alpha = (predicted_next - float(self.mid)) * self.ALPHA_SCALE
        return alpha, fit_quality, volatility

    def classify_state(self, alpha: float, fit_quality: float, volatility: float) -> str:
        if volatility >= self.TOXIC_VOLATILITY_THRESHOLD:
            return "volatile"
        if alpha >= self.TREND_EDGE_THRESHOLD and fit_quality >= self.FIT_THRESHOLD:
            return "trend_up"
        if alpha <= -self.TREND_EDGE_THRESHOLD and fit_quality >= self.FIT_THRESHOLD:
            return "trend_down"
        return "range"

    def target_position(self, regime: str, alpha: float) -> int:
        if regime == "trend_up":
            return self.STRONG_TREND_POSITION if alpha >= self.STRONG_TREND_EDGE else self.TREND_POSITION
        if regime == "trend_down":
            return -self.STRONG_TREND_POSITION if alpha <= -self.STRONG_TREND_EDGE else -self.TREND_POSITION
        return 0

    def reservation_price(self, regime: str, alpha: float, target_position: int) -> float:
        base_fair = (
            self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
            + alpha
        )
        base_fair += (target_position - self.projected_position()) / self.POSITION_BIAS_DIVISOR
        return base_fair - (self.projected_position() * self.INVENTORY_SKEW)

    def execution_edge(self, regime: str, volatility: float) -> float:
        edge = self.BASE_EDGE
        edge += self.VOL_EDGE_COEF * min(3.0, volatility)
        edge += self.INV_EDGE_COEF * (min(self.position_limit, abs(self.projected_position())) / self.position_limit)

        if int(self.spread) >= 14:
            edge += 0.4
        if regime in {"trend_up", "trend_down"}:
            edge += self.TREND_EDGE_BONUS
        elif regime == "volatile":
            edge += self.VOLATILE_EDGE_BONUS

        return min(self.MAX_EDGE, edge)

    def passive_size(self, side: str, regime: str) -> int:
        size = self.PASSIVE_SIZE + (1 if regime in {"trend_up", "trend_down"} else 0)
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

    def allow_passive(self, side: str) -> bool:
        position = self.projected_position()
        if side == "BUY" and position >= self.soft_limit:
            return False
        if side == "SELL" and position <= -self.soft_limit:
            return False
        return True

    def take_orders(
        self,
        regime: str,
        reservation: float,
        execution_edge: float,
        target_position: int,
        alpha: float,
    ) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False
        take_edge = max(0.75, execution_edge * self.TAKE_EDGE_FRACTION)

        if int(self.best_ask) <= reservation - take_edge and self.buy_capacity > 0:
            if regime == "range" or self.projected_position() < target_position:
                quantity = min(self.best_ask_volume, int(self.MAX_TAKE_SIZE))
                if regime != "range":
                    quantity = min(quantity, max(1, target_position - self.projected_position()))
                before = self.buy_capacity
                self.add_buy(int(self.best_ask), quantity)
                took_buy = self.buy_capacity < before

        if int(self.best_bid) >= reservation + take_edge and self.sell_capacity > 0:
            if regime == "range" or self.projected_position() > target_position:
                min_sell_edge = reservation + take_edge
                if regime == "trend_up" and alpha >= self.TREND_EDGE_THRESHOLD:
                    min_sell_edge += 0.6
                quantity = min(self.best_bid_volume, int(self.MAX_TAKE_SIZE))
                if regime != "range":
                    quantity = min(quantity, max(1, self.projected_position() - target_position))
                if int(self.best_bid) >= min_sell_edge:
                    before = self.sell_capacity
                    self.add_sell(int(self.best_bid), quantity)
                    took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def passive_quotes(
        self,
        reservation: float,
        execution_edge: float,
        regime: str,
        target_position: int,
        alpha: float,
    ) -> Tuple[Optional[int], Optional[int]]:
        buy_quote = math.floor(reservation - execution_edge)
        sell_quote = math.ceil(reservation + execution_edge)
        buy_quote, sell_quote = self.clamp_inside_spread(buy_quote, sell_quote)

        position = self.projected_position()
        if regime == "trend_up" and sell_quote is not None and position > 0 and alpha >= self.TREND_EDGE_THRESHOLD:
            sell_quote += 1
        elif regime == "trend_down" and buy_quote is not None and position < 0 and alpha <= -self.TREND_EDGE_THRESHOLD:
            buy_quote -= 1

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        alpha, fit_quality, volatility = self.regression_alpha()
        regime = self.classify_state(alpha, fit_quality, volatility)
        target_position = self.target_position(regime, alpha)
        reservation = self.reservation_price(regime, alpha, target_position)
        execution_edge = self.execution_edge(regime, volatility)
        took_buy, took_sell = self.take_orders(
            regime,
            reservation,
            execution_edge,
            target_position,
            alpha,
        )

        buy_quote, sell_quote = self.passive_quotes(
            reservation,
            execution_edge,
            regime,
            target_position,
            alpha,
        )
        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.allow_passive("BUY")
        ):
            if regime == "range" or position < target_position:
                quantity = min(self.passive_size("BUY", regime), self.buy_capacity)
                if regime != "range":
                    quantity = min(quantity, max(1, target_position - position))
                self.add_buy(buy_quote, quantity)

        position = self.projected_position()
        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.allow_passive("SELL")
        ):
            if regime == "range" or position > target_position:
                quantity = min(self.passive_size("SELL", regime), self.sell_capacity)
                if regime != "range":
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
