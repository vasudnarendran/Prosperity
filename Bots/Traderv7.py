from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import math


class Trader:
    POSITION_LIMITS: Dict[str, int] = {
        "EMERALDS": 80,
        "TOMATOES": 80,
    }

    REFERENCE_PRICES: Dict[str, float] = {
        "EMERALDS": 10000.0,
    }

    REFERENCE_WEIGHT: Dict[str, float] = {
        "EMERALDS": 0.8,
    }

    MID_WEIGHT: Dict[str, float] = {
        "EMERALDS": 0.2,
    }

    TAKE_EDGE: Dict[str, float] = {
        "EMERALDS": 1.0,
        "TOMATOES": 1.5,
    }

    QUOTE_EDGE: Dict[str, float] = {
        "EMERALDS": 2.0,
        "TOMATOES": 2.0,
    }

    MAX_QUOTE_EDGE: Dict[str, float] = {
        "EMERALDS": 4.0,
        "TOMATOES": 4.0,
    }

    INVENTORY_SKEW: Dict[str, float] = {
        "EMERALDS": 0.16,
        "TOMATOES": 0.10,
    }

    PASSIVE_SIZE: Dict[str, int] = {
        "EMERALDS": 8,
        "TOMATOES": 7,
    }

    MAX_TAKE_SIZE: Dict[str, int] = {
        "EMERALDS": 10,
        "TOMATOES": 8,
    }

    SOFT_LIMIT_RATIO = 0.5
    EMERALDS_FAIR_VALUE = 10000.0
    EMERALDS_RICH_BID = 10000
    EMERALDS_CHEAP_ASK = 10000

    def get_best_prices(self, order_depth: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
        return best_bid, best_ask

    def get_fair_value(
        self,
        product: str,
        best_bid: Optional[int],
        best_ask: Optional[int],
    ) -> Optional[float]:
        reference_price = self.REFERENCE_PRICES.get(product)

        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2
            if reference_price is None:
                return mid_price

            reference_weight = self.REFERENCE_WEIGHT.get(product, 0.8)
            mid_weight = self.MID_WEIGHT.get(product, 0.2)
            return reference_weight * reference_price + mid_weight * mid_price

        if reference_price is not None:
            return reference_price

        if best_bid is not None:
            return float(best_bid)

        if best_ask is not None:
            return float(best_ask)

        return None

    def get_inventory_adjusted_fair_value(
        self,
        product: str,
        fair_value: float,
        position: int,
    ) -> float:
        skew = self.INVENTORY_SKEW.get(product, 0.0)
        return fair_value - (position * skew)

    def get_effective_take_edge(
        self,
        product: str,
        side: str,
        position: int,
        spread: int,
    ) -> float:
        edge = self.TAKE_EDGE.get(product, 1.0)

        if spread >= 14:
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

        return max(0.5, edge)

    def get_quote_edge(self, product: str, spread: int) -> float:
        base_edge = self.QUOTE_EDGE.get(product, 2.0)
        max_edge = self.MAX_QUOTE_EDGE.get(product, 4.0)
        return min(max_edge, max(base_edge, spread / 4))

    def should_place_passive_order(
        self,
        side: str,
        position: int,
        limit: int,
    ) -> bool:
        soft_limit = int(limit * self.SOFT_LIMIT_RATIO)

        if side == "BUY" and position >= soft_limit:
            return False

        if side == "SELL" and position <= -soft_limit:
            return False

        return True

    def get_passive_quotes(
        self,
        product: str,
        adjusted_fair_value: float,
        best_bid: int,
        best_ask: int,
        position: int,
        limit: int,
    ) -> Tuple[Optional[int], Optional[int]]:
        spread = best_ask - best_bid
        quote_edge = self.get_quote_edge(product, spread)

        buy_quote = math.floor(adjusted_fair_value - quote_edge)
        sell_quote = math.ceil(adjusted_fair_value + quote_edge)

        buy_quote = max(buy_quote, best_bid + 1)
        sell_quote = min(sell_quote, best_ask - 1)

        soft_limit = int(limit * self.SOFT_LIMIT_RATIO)
        if position >= soft_limit:
            sell_quote = max(best_bid + 1, sell_quote - 1)
        elif position <= -soft_limit:
            buy_quote = min(best_ask - 1, buy_quote + 1)

        final_buy_quote = buy_quote if buy_quote < best_ask else None
        final_sell_quote = sell_quote if sell_quote > best_bid else None
        return final_buy_quote, final_sell_quote

    def get_passive_size(
        self,
        product: str,
        position: int,
        side: str,
        spread: int,
    ) -> int:
        base_size = self.PASSIVE_SIZE.get(product, 5)

        if spread >= 14:
            base_size += 1

        if side == "BUY":
            if position <= -20:
                base_size += 1
            elif position >= 20:
                base_size = max(1, base_size - 2)
        else:
            if position >= 20:
                base_size += 1
            elif position <= -20:
                base_size = max(1, base_size - 2)

        return max(1, base_size)

    def run_emeralds(
        self,
        product: str,
        order_depth: OrderDepth,
        position: int,
    ) -> List[Order]:
        orders: List[Order] = []
        best_bid, best_ask = self.get_best_prices(order_depth)
        if best_bid is None or best_ask is None:
            return orders

        limit = self.POSITION_LIMITS[product]
        buy_capacity = limit - position
        sell_capacity = limit + position
        best_bid_amount = order_depth.buy_orders[best_bid]
        best_ask_amount = -order_depth.sell_orders[best_ask]

        adjusted_fair_value = self.get_inventory_adjusted_fair_value(
            product,
            self.EMERALDS_FAIR_VALUE,
            position,
        )

        cheap_ask_state = best_ask <= self.EMERALDS_CHEAP_ASK
        rich_bid_state = best_bid >= self.EMERALDS_RICH_BID

        took_buy = False
        took_sell = False

        if cheap_ask_state and buy_capacity > 0:
            buy_volume = min(best_ask_amount, 14, buy_capacity)
            if position < 0:
                buy_volume = min(best_ask_amount, 18, buy_capacity)
            if buy_volume > 0:
                orders.append(Order(product, best_ask, buy_volume))
                took_buy = True

        if rich_bid_state and sell_capacity > 0:
            sell_volume = min(best_bid_amount, 14, sell_capacity)
            if position > 0:
                sell_volume = min(best_bid_amount, 18, sell_capacity)
            if sell_volume > 0:
                orders.append(Order(product, best_bid, -sell_volume))
                took_sell = True

        buy_quote = 9996
        sell_quote = 10004

        if cheap_ask_state:
            buy_quote = 9997
            sell_quote = 10005
        elif rich_bid_state:
            buy_quote = 9995
            sell_quote = 10003

        soft_limit = int(limit * self.SOFT_LIMIT_RATIO)
        if position >= soft_limit:
            sell_quote = max(best_bid + 1, sell_quote - 1)
        elif position <= -soft_limit:
            buy_quote = min(best_ask - 1, buy_quote + 1)

        if (
            not took_buy
            and buy_capacity > 0
            and buy_quote < best_ask
            and self.should_place_passive_order("BUY", position, limit)
        ):
            buy_size = min(8 if rich_bid_state else 10, buy_capacity)
            if position <= -20:
                buy_size = min(buy_size + 2, buy_capacity)
            if buy_size > 0:
                orders.append(Order(product, buy_quote, buy_size))

        if (
            not took_sell
            and sell_capacity > 0
            and sell_quote > best_bid
            and self.should_place_passive_order("SELL", position, limit)
        ):
            sell_size = min(8 if cheap_ask_state else 10, sell_capacity)
            if position >= 20:
                sell_size = min(sell_size + 2, sell_capacity)
            if sell_size > 0:
                orders.append(Order(product, sell_quote, -sell_size))

        return orders

    def run_generic(
        self,
        product: str,
        order_depth: OrderDepth,
        position: int,
    ) -> List[Order]:
        orders: List[Order] = []
        best_bid, best_ask = self.get_best_prices(order_depth)

        if best_bid is None or best_ask is None:
            return orders

        limit = self.POSITION_LIMITS.get(product, 80)
        buy_capacity = limit - position
        sell_capacity = limit + position
        spread = best_ask - best_bid

        fair_value = self.get_fair_value(product, best_bid, best_ask)
        if fair_value is None:
            return orders

        adjusted_fair_value = self.get_inventory_adjusted_fair_value(
            product,
            fair_value,
            position,
        )

        took_buy = False
        took_sell = False

        best_ask_amount = -order_depth.sell_orders[best_ask]
        buy_take_edge = self.get_effective_take_edge(product, "BUY", position, spread)
        if best_ask <= adjusted_fair_value - buy_take_edge and buy_capacity > 0:
            buy_volume = min(
                best_ask_amount,
                self.MAX_TAKE_SIZE.get(product, 10),
                buy_capacity,
            )
            if buy_volume > 0:
                orders.append(Order(product, best_ask, buy_volume))
                took_buy = True

        best_bid_amount = order_depth.buy_orders[best_bid]
        sell_take_edge = self.get_effective_take_edge(product, "SELL", position, spread)
        if best_bid >= adjusted_fair_value + sell_take_edge and sell_capacity > 0:
            sell_volume = min(
                best_bid_amount,
                self.MAX_TAKE_SIZE.get(product, 10),
                sell_capacity,
            )
            if sell_volume > 0:
                orders.append(Order(product, best_bid, -sell_volume))
                took_sell = True

        buy_quote, sell_quote = self.get_passive_quotes(
            product,
            adjusted_fair_value,
            best_bid,
            best_ask,
            position,
            limit,
        )

        if (
            not took_buy
            and buy_quote is not None
            and buy_capacity > 0
            and self.should_place_passive_order("BUY", position, limit)
        ):
            passive_buy_size = min(
                self.get_passive_size(product, position, "BUY", spread),
                buy_capacity,
            )
            if passive_buy_size > 0:
                orders.append(Order(product, buy_quote, passive_buy_size))

        if (
            not took_sell
            and sell_quote is not None
            and sell_capacity > 0
            and self.should_place_passive_order("SELL", position, limit)
        ):
            passive_sell_size = min(
                self.get_passive_size(product, position, "SELL", spread),
                sell_capacity,
            )
            if passive_sell_size > 0:
                orders.append(Order(product, sell_quote, -passive_sell_size))

        return orders

    def run(self, state: TradingState):
        result = {}

        for product, order_depth in state.order_depths.items():
            position = state.position.get(product, 0)
            if product == "EMERALDS":
                result[product] = self.run_emeralds(product, order_depth, position)
            else:
                result[product] = self.run_generic(product, order_depth, position)

        traderData = ""
        conversions = 0
        return result, conversions, traderData
