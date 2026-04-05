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
    REFERENCE_WEIGHT = 0.82
    MID_WEIGHT = 0.18
    MICRO_WEIGHT = 0.00
    INVENTORY_SKEW = 0.12
    BASE_TAKE_EDGE = 1.00
    BASE_QUOTE_EDGE = 2.0
    MIN_QUOTE_EDGE = 2.0
    MAX_QUOTE_EDGE = 4.0
    TAKE_SIZE = 10
    PASSIVE_SIZE = 7
    REBALANCE_SIZE = 8

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
            edge = max(self.MIN_QUOTE_EDGE, edge - 0.5)

        return min(self.MAX_QUOTE_EDGE, edge)

    def passive_quotes(self, adjusted_fair: float) -> Tuple[Optional[int], Optional[int]]:
        buy_quote = math.floor(adjusted_fair - self.quote_edge())
        sell_quote = math.ceil(adjusted_fair + self.quote_edge())

        for price, volume in self.buy_levels:
            overbid = price + 1
            if volume > 1 and overbid < self.REFERENCE_PRICE:
                buy_quote = max(buy_quote, overbid)
                break
            if price < self.REFERENCE_PRICE:
                buy_quote = max(buy_quote, price)
                break

        for price, volume in self.sell_levels:
            underbid = price - 1
            if volume > 1 and underbid > self.REFERENCE_PRICE:
                sell_quote = min(sell_quote, underbid)
                break
            if price > self.REFERENCE_PRICE:
                sell_quote = min(sell_quote, price)
                break

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
        if int(self.spread) >= 10:
            size += 1

        position = self.projected_position()
        if side == "BUY":
            if position <= -20:
                size += 1
            elif position >= 20:
                size = max(2, size - 2)
        else:
            if position >= 20:
                size += 1
            elif position <= -20:
                size = max(2, size - 2)

        return size

    def take_book(self, adjusted_fair: float) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        for ask_price, ask_volume in self.sell_levels:
            position = self.projected_position()
            if self.buy_capacity <= 0:
                break

            if ask_price <= adjusted_fair - self.take_edge("BUY"):
                before = self.buy_capacity
                self.add_buy(ask_price, min(ask_volume, self.TAKE_SIZE))
                took_buy = took_buy or self.buy_capacity < before
                continue

            if ask_price == int(self.REFERENCE_PRICE) and position < 0:
                before = self.buy_capacity
                self.add_buy(ask_price, min(ask_volume, abs(position), self.REBALANCE_SIZE))
                took_buy = took_buy or self.buy_capacity < before
            break

        for bid_price, bid_volume in self.buy_levels:
            position = self.projected_position()
            if self.sell_capacity <= 0:
                break

            if bid_price >= adjusted_fair + self.take_edge("SELL"):
                before = self.sell_capacity
                self.add_sell(bid_price, min(bid_volume, self.TAKE_SIZE))
                took_sell = took_sell or self.sell_capacity < before
                continue

            if bid_price == int(self.REFERENCE_PRICE) and position > 0:
                before = self.sell_capacity
                self.add_sell(bid_price, min(bid_volume, position, self.REBALANCE_SIZE))
                took_sell = took_sell or self.sell_capacity < before
            break

        return took_buy, took_sell

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        adjusted_fair = self.adjusted_fair_value()
        took_buy, took_sell = self.take_book(adjusted_fair)
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
    BASE_QUOTE_EDGE = 2.0
    MAX_QUOTE_EDGE = 5.0
    BASE_TAKE_EDGE = 1.25
    PASSIVE_SIZE = 7
    MAX_TAKE_SIZE = 10
    HALF_LIMIT = 40

    def regime(self) -> str:
        bullish_votes = 0
        bearish_votes = 0

        if self.momentum >= 1.5:
            bullish_votes += 1
        if self.short_momentum >= 0.8:
            bullish_votes += 1
        if self.imbalance >= 0.12:
            bullish_votes += 1
        if float(self.micro) >= float(self.mid):
            bullish_votes += 1

        if self.momentum <= -1.5:
            bearish_votes += 1
        if self.short_momentum <= -0.8:
            bearish_votes += 1
        if self.imbalance <= -0.12:
            bearish_votes += 1
        if float(self.micro) <= float(self.mid):
            bearish_votes += 1

        if int(self.spread) >= 15 and max(bullish_votes, bearish_votes) <= 2:
            return "toxic"
        if bullish_votes >= 4:
            return "trend_up_strong"
        if bullish_votes >= 3:
            return "trend_up"
        if bearish_votes >= 4:
            return "trend_down_strong"
        if bearish_votes >= 3:
            return "trend_down"
        return "mean_revert"

    def target_band(self, regime: str) -> Tuple[int, int]:
        if regime == "trend_up_strong":
            return 20, self.HALF_LIMIT
        if regime == "trend_up":
            return 10, 26
        if regime == "trend_down_strong":
            return -self.HALF_LIMIT, -20
        if regime == "trend_down":
            return -26, -10
        if regime == "toxic":
            return -8, 8
        return -12, 12

    def target_position(self, regime: str) -> int:
        lower, upper = self.target_band(regime)
        position = self.projected_position()
        if position < lower:
            return lower
        if position > upper:
            return upper
        if regime.startswith("trend_up"):
            return upper
        if regime.startswith("trend_down"):
            return lower
        return 0

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

        if regime == "trend_up_strong":
            edge += -0.5 if side == "BUY" else 0.7
        elif regime == "trend_up":
            edge += -0.4 if side == "BUY" else 0.6
        elif regime == "trend_down_strong":
            edge += -0.5 if side == "SELL" else 0.7
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
        elif regime in {"trend_up_strong", "trend_down_strong"}:
            edge += 0.35
        elif regime in {"trend_up", "trend_down"}:
            edge += 0.25

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
        if regime in {"trend_up_strong", "trend_up"}:
            if buy_quote is not None and position < target_position:
                buy_quote = min(int(self.best_ask) - 1, max(int(self.best_bid) + 1, buy_quote + 1))
            if position < 16:
                sell_quote = None
        elif regime in {"trend_down_strong", "trend_down"}:
            if sell_quote is not None and position > target_position:
                sell_quote = max(int(self.best_bid) + 1, min(int(self.best_ask) - 1, sell_quote - 1))
            if position > -16:
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
        elif regime in {"trend_up_strong", "trend_down_strong", "trend_up", "trend_down"}:
            size = max(1, size - 1)

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

    def trend_take(self, regime: str, target_position: int, adjusted_fair: float) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False
        position = self.projected_position()

        if regime in {"trend_up_strong", "trend_up"} and position < target_position and self.buy_capacity > 0:
            edge = self.take_edge("BUY", regime)
            if int(self.best_ask) <= adjusted_fair - edge + 1.0:
                max_target = target_position - position
                take_limit = self.MAX_TAKE_SIZE + (2 if regime == "trend_up_strong" else 0)
                before = self.buy_capacity
                self.add_buy(int(self.best_ask), min(self.best_ask_volume, take_limit, max_target))
                took_buy = self.buy_capacity < before

        position = self.projected_position()
        if regime in {"trend_down_strong", "trend_down"} and position > target_position and self.sell_capacity > 0:
            edge = self.take_edge("SELL", regime)
            if int(self.best_bid) >= adjusted_fair + edge - 1.0:
                max_target = position - target_position
                take_limit = self.MAX_TAKE_SIZE + (2 if regime == "trend_down_strong" else 0)
                before = self.sell_capacity
                self.add_sell(int(self.best_bid), min(self.best_bid_volume, take_limit, max_target))
                took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def mean_reversion_take(self, regime: str, adjusted_fair: float) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        if int(self.best_ask) <= adjusted_fair - self.take_edge("BUY", regime) and self.buy_capacity > 0:
            before = self.buy_capacity
            self.add_buy(int(self.best_ask), min(self.best_ask_volume, self.MAX_TAKE_SIZE))
            took_buy = self.buy_capacity < before

        if int(self.best_bid) >= adjusted_fair + self.take_edge("SELL", regime) and self.sell_capacity > 0:
            before = self.sell_capacity
            self.add_sell(int(self.best_bid), min(self.best_bid_volume, self.MAX_TAKE_SIZE))
            took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        regime = self.regime()
        target_position = self.target_position(regime)
        adjusted_fair = self.adjusted_fair_value(target_position)

        if regime in {"trend_up_strong", "trend_up", "trend_down_strong", "trend_down"}:
            took_buy, took_sell = self.trend_take(regime, target_position, adjusted_fair)
        else:
            took_buy, took_sell = self.mean_reversion_take(regime, adjusted_fair)

        buy_quote, sell_quote = self.passive_quotes(adjusted_fair, regime, target_position)
        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and not (regime == "toxic" and abs(position) <= 6)
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
            and not (regime == "toxic" and abs(position) <= 6)
        ):
            if regime == "mean_revert" or position > target_position:
                quantity = min(self.passive_size("SELL", regime), self.sell_capacity)
                if regime != "mean_revert":
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
