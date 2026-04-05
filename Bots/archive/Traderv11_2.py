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

        self.best_bid: Optional[int] = None
        self.best_ask: Optional[int] = None
        self.best_bid_volume = 0
        self.best_ask_volume = 0
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

        self.best_bid = max(self.order_depth.buy_orders.keys()) if self.order_depth.buy_orders else None
        self.best_ask = min(self.order_depth.sell_orders.keys()) if self.order_depth.sell_orders else None
        if self.best_bid is None or self.best_ask is None:
            return

        self.best_bid_volume = self.order_depth.buy_orders[self.best_bid]
        self.best_ask_volume = -self.order_depth.sell_orders[self.best_ask]
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

    def clamp_inside_spread(self, buy_quote: Optional[int], sell_quote: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
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
        return self.fair_value() - (self.position * self.INVENTORY_SKEW)

    def take_edge(self, side: str) -> float:
        edge = self.BASE_TAKE_EDGE
        if int(self.spread) >= 14:
            edge += 0.5

        if side == "BUY":
            if self.position <= -20:
                edge -= 0.5
            elif self.position >= 20:
                edge += 0.5
        else:
            if self.position >= 20:
                edge -= 0.5
            elif self.position <= -20:
                edge += 0.5

        if side == "BUY" and int(self.best_ask) <= 10000:
            edge += 0.25

        return max(0.5, edge)

    def quote_edge(self) -> float:
        edge = max(self.BASE_QUOTE_EDGE, float(self.spread) / 4.0)
        edge = min(self.MAX_QUOTE_EDGE, edge)

        if abs(self.position) >= self.soft_limit:
            edge += 0.5

        if int(self.best_ask) <= 10000 or int(self.best_bid) >= 10000:
            edge = max(1.5, edge - 0.5)

        return min(self.MAX_QUOTE_EDGE, edge)

    def passive_size(self, side: str) -> int:
        size = self.PASSIVE_SIZE
        if int(self.spread) >= 8:
            size += 1

        if side == "BUY":
            if self.position <= -20:
                size += 1
            elif self.position >= 20:
                size = max(1, size - 2)
        else:
            if self.position >= 20:
                size += 1
            elif self.position <= -20:
                size = max(1, size - 2)

        return max(1, size)

    def passive_quotes(self, adjusted_fair: float) -> Tuple[Optional[int], Optional[int]]:
        buy_quote = math.floor(adjusted_fair - self.quote_edge())
        sell_quote = math.ceil(adjusted_fair + self.quote_edge())

        if self.position >= self.soft_limit:
            sell_quote -= 1
        elif self.position <= -self.soft_limit:
            buy_quote += 1

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        adjusted_fair = self.adjusted_fair_value()
        took_buy = False
        took_sell = False

        if int(self.best_ask) <= adjusted_fair - self.take_edge("BUY") and self.buy_capacity > 0:
            take_limit = self.MAX_TAKE_SIZE
            self.add_buy(int(self.best_ask), min(self.best_ask_volume, take_limit))
            took_buy = self.buy_capacity < (self.position_limit - self.position)

        if int(self.best_bid) >= adjusted_fair + self.take_edge("SELL") and self.sell_capacity > 0:
            take_limit = self.MAX_TAKE_SIZE
            self.add_sell(int(self.best_bid), min(self.best_bid_volume, take_limit))
            took_sell = self.sell_capacity < (self.position_limit + self.position)

        buy_quote, sell_quote = self.passive_quotes(adjusted_fair)

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.position < self.soft_limit
        ):
            self.add_buy(buy_quote, self.passive_size("BUY"))

        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.position > -self.soft_limit
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

    def classify_state(self) -> str:
        if float(self.spread) >= 15 and abs(self.momentum) < 1.5:
            return "toxic"
        if self.momentum >= 1.5 and self.imbalance >= 0.15 and float(self.micro) >= float(self.mid):
            return "trend_up"
        if self.momentum <= -1.5 and self.imbalance <= -0.15 and float(self.micro) <= float(self.mid):
            return "trend_down"
        return "mean_revert"

    def target_band(self, regime: str) -> Tuple[int, int]:
        if regime == "trend_up":
            return (20, 36) if self.momentum >= 4.0 else (10, 26)
        if regime == "trend_down":
            return (-36, -20) if self.momentum <= -4.0 else (-26, -10)
        if regime == "toxic":
            return -8, 8
        return -10, 10

    def target_position(self, regime: str) -> int:
        lower, upper = self.target_band(regime)
        if self.position < lower:
            return lower
        if self.position > upper:
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
        fair += (target_position - self.position) / 18.0
        return fair

    def adjusted_fair_value(self, target_position: int) -> float:
        return self.fair_value(target_position) - (self.position * self.INVENTORY_SKEW)

    def take_edge(self, side: str, regime: str) -> float:
        edge = self.BASE_TAKE_EDGE
        if int(self.spread) >= 14:
            edge += 0.5

        if side == "BUY":
            if self.position <= -20:
                edge -= 0.5
            elif self.position >= 20:
                edge += 0.5
        else:
            if self.position >= 20:
                edge -= 0.5
            elif self.position <= -20:
                edge += 0.5

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

        edge += 0.20 * self.toxicity()
        return max(0.5, edge)

    def quote_edge(self, regime: str) -> float:
        edge = max(self.BASE_QUOTE_EDGE, float(self.spread) / 3.5)
        edge = min(self.MAX_QUOTE_EDGE, edge)

        if abs(self.position) >= self.soft_limit:
            edge += 0.5

        if regime == "toxic":
            edge += 1.0
        elif regime in {"trend_up", "trend_down"}:
            edge += 0.25

        edge += 0.35 * self.toxicity()
        return min(self.MAX_QUOTE_EDGE, edge)

    def passive_quotes(self, adjusted_fair: float, regime: str, target_position: int) -> Tuple[Optional[int], Optional[int]]:
        buy_quote = math.floor(adjusted_fair - self.quote_edge(regime))
        sell_quote = math.ceil(adjusted_fair + self.quote_edge(regime))
        buy_quote, sell_quote = self.clamp_inside_spread(buy_quote, sell_quote)

        if regime == "trend_up":
            if self.position < target_position and buy_quote is not None:
                buy_quote = min(int(self.best_ask) - 1, max(int(self.best_bid) + 1, buy_quote + 1))
            if self.position <= 16:
                sell_quote = None
        elif regime == "trend_down":
            if self.position > target_position and sell_quote is not None:
                sell_quote = max(int(self.best_bid) + 1, min(int(self.best_ask) - 1, sell_quote - 1))
            if self.position >= -16:
                buy_quote = None
        elif regime == "toxic" and abs(self.position) <= 6:
            buy_quote = None
            sell_quote = None

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def allow_passive(self, side: str, regime: str) -> bool:
        if side == "BUY" and self.position >= self.soft_limit:
            return False
        if side == "SELL" and self.position <= -self.soft_limit:
            return False
        if regime == "toxic" and abs(self.position) <= 6:
            return False
        return True

    def passive_size(self, side: str, regime: str) -> int:
        size = self.PASSIVE_SIZE
        if int(self.spread) >= 14:
            size += 1

        if regime == "toxic":
            size = max(1, size - 3)
        elif regime in {"trend_up", "trend_down"}:
            size = max(1, size - 1)

        size = max(1, int(size - self.toxicity()))

        if side == "BUY":
            if self.position <= -20:
                size += 1
            elif self.position >= 20:
                size = max(1, size - 2)
        else:
            if self.position >= 20:
                size += 1
            elif self.position <= -20:
                size = max(1, size - 2)

        return max(1, size)

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        regime = self.classify_state()
        target_position = self.target_position(regime)
        adjusted_fair = self.adjusted_fair_value(target_position)

        took_buy = False
        took_sell = False

        if int(self.best_ask) <= adjusted_fair - self.take_edge("BUY", regime) and self.buy_capacity > 0:
            take_limit = self.MAX_TAKE_SIZE + (2 if regime == "trend_up" else 0)
            if regime != "mean_revert" and self.position >= target_position:
                pass
            else:
                quantity = min(self.best_ask_volume, take_limit)
                if regime != "mean_revert":
                    quantity = min(quantity, max(1, target_position - self.position))
                before = self.buy_capacity
                self.add_buy(int(self.best_ask), quantity)
                took_buy = self.buy_capacity < before

        if int(self.best_bid) >= adjusted_fair + self.take_edge("SELL", regime) and self.sell_capacity > 0:
            take_limit = self.MAX_TAKE_SIZE + (2 if regime == "trend_down" else 0)
            if regime != "mean_revert" and self.position <= target_position:
                pass
            else:
                quantity = min(self.best_bid_volume, take_limit)
                if regime != "mean_revert":
                    quantity = min(quantity, max(1, self.position - target_position))
                before = self.sell_capacity
                self.add_sell(int(self.best_bid), quantity)
                took_sell = self.sell_capacity < before

        buy_quote, sell_quote = self.passive_quotes(adjusted_fair, regime, target_position)
        allow_mean_revert_quotes = regime == "mean_revert"

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.allow_passive("BUY", regime)
        ):
            if allow_mean_revert_quotes or self.position < target_position:
                quantity = min(self.passive_size("BUY", regime), self.buy_capacity)
                if not allow_mean_revert_quotes:
                    quantity = min(quantity, max(1, target_position - self.position))
                self.add_buy(buy_quote, quantity)

        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.allow_passive("SELL", regime)
        ):
            if allow_mean_revert_quotes or self.position > target_position:
                quantity = min(self.passive_size("SELL", regime), self.sell_capacity)
                if not allow_mean_revert_quotes:
                    quantity = min(quantity, max(1, self.position - target_position))
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

        for product, order_depth in state.order_depths.items():
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
