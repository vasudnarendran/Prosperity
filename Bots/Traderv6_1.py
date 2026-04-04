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

    # Small fair-value experiment for EMERALDS.
    # Current test: 0.7 reference + 0.3 live mid
    REFERENCE_WEIGHT: Dict[str, float] = {
        "EMERALDS": 0.7,
    }

    MID_WEIGHT: Dict[str, float] = {
        "EMERALDS": 0.3,
    }

    TAKE_EDGE: Dict[str, float] = {
        "EMERALDS": 1.0,
        "TOMATOES": 1.5,
    }

    QUOTE_EDGE: Dict[str, float] = {
        "EMERALDS": 2.0,
        "TOMATOES": 2.0,
    }

    INVENTORY_SKEW: Dict[str, float] = {
        "EMERALDS": 0.10,
        "TOMATOES": 0.08,
    }

    PASSIVE_SIZE: Dict[str, int] = {
        "EMERALDS": 8,
        "TOMATOES": 8,
    }

    MAX_TAKE_SIZE: Dict[str, int] = {
        "EMERALDS": 12,
        "TOMATOES": 10,
    }

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

    def get_passive_quotes(
        self,
        product: str,
        adjusted_fair_value: float,
        best_bid: Optional[int],
        best_ask: Optional[int],
    ) -> Tuple[Optional[int], Optional[int]]:
        quote_edge = self.QUOTE_EDGE.get(product, 2.0)

        buy_quote = math.floor(adjusted_fair_value - quote_edge)
        sell_quote = math.ceil(adjusted_fair_value + quote_edge)

        if best_bid is not None:
            buy_quote = max(buy_quote, best_bid + 1)
            sell_quote = max(sell_quote, best_bid + 1)

        if best_ask is not None:
            buy_quote = min(buy_quote, best_ask - 1)
            sell_quote = min(sell_quote, best_ask - 1)

        final_buy_quote = buy_quote if best_ask is None or buy_quote < best_ask else None
        final_sell_quote = sell_quote if best_bid is None or sell_quote > best_bid else None
        return final_buy_quote, final_sell_quote

    def get_passive_size(self, product: str, position: int, side: str) -> int:
        base_size = self.PASSIVE_SIZE.get(product, 5)

        if side == "BUY":
            return max(1, base_size + max(0, -position // 20))

        return max(1, base_size + max(0, position // 20))

    def run(self, state: TradingState):
        result = {}

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []
            best_bid, best_ask = self.get_best_prices(order_depth)

            if best_bid is None or best_ask is None:
                result[product] = orders
                continue

            position = state.position.get(product, 0)
            limit = self.POSITION_LIMITS.get(product, 80)
            buy_capacity = limit - position
            sell_capacity = limit + position

            fair_value = self.get_fair_value(product, best_bid, best_ask)
            if fair_value is None:
                result[product] = orders
                continue

            adjusted_fair_value = self.get_inventory_adjusted_fair_value(
                product,
                fair_value,
                position,
            )
            take_edge = self.TAKE_EDGE.get(product, 1.0)

            best_ask_amount = -order_depth.sell_orders[best_ask]
            if best_ask <= adjusted_fair_value - take_edge and buy_capacity > 0:
                buy_volume = min(
                    best_ask_amount,
                    self.MAX_TAKE_SIZE.get(product, 10),
                    buy_capacity,
                )
                if buy_volume > 0:
                    orders.append(Order(product, best_ask, buy_volume))

            best_bid_amount = order_depth.buy_orders[best_bid]
            if best_bid >= adjusted_fair_value + take_edge and sell_capacity > 0:
                sell_volume = min(
                    best_bid_amount,
                    self.MAX_TAKE_SIZE.get(product, 10),
                    sell_capacity,
                )
                if sell_volume > 0:
                    orders.append(Order(product, best_bid, -sell_volume))

            buy_quote, sell_quote = self.get_passive_quotes(
                product,
                adjusted_fair_value,
                best_bid,
                best_ask,
            )

            if buy_quote is not None and buy_capacity > 0:
                passive_buy_size = min(
                    self.get_passive_size(product, position, "BUY"),
                    buy_capacity,
                )
                if passive_buy_size > 0:
                    orders.append(Order(product, buy_quote, passive_buy_size))

            if sell_quote is not None and sell_capacity > 0:
                passive_sell_size = min(
                    self.get_passive_size(product, position, "SELL"),
                    sell_capacity,
                )
                if passive_sell_size > 0:
                    orders.append(Order(product, sell_quote, -passive_sell_size))

            result[product] = orders

        traderData = ""
        conversions = 0
        return result, conversions, traderData
