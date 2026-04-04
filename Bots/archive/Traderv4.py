from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string

class Trader:

    def bid(self):
        return 15
    
    class Trader:
        POSITION_LIMITS = {
            "EMERALDS": 80,
            "TOMATOES": 80,
        }

        def get_best_bid_ask(self, order_depth: OrderDepth):
            if not order_depth.buy_orders or not order_depth.sell_orders:
                return None, None
            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            return best_bid, best_ask

        def get_mid_price(self, order_depth: OrderDepth):
            best_bid, best_ask = self.get_best_bid_ask(order_depth)
            if best_bid is None or best_ask is None:
                return None
            return (best_bid + best_ask) / 2

        def get_position(self, state: TradingState, product: str) -> int:
            return state.position.get(product, 0)

        def get_acceptable_price(self, product: str, order_depth: OrderDepth):
            mid_price = self.get_mid_price(order_depth)
            if mid_price is None:
                return None

            if product == "EMERALDS":
                # Stable product: use a fixed anchor or a slowly changing value
                return 10000

            if product == "TOMATOES":
                # Fluctuating product: start with the current midpoint
                return mid_price

            return mid_price

        def market_make(self, product: str, acceptable_price: float, state: TradingState):
            orders = []
            position = self.get_position(state, product)
            limit = self.POSITION_LIMITS[product]

            buy_price = int(acceptable_price - 1)
            sell_price = int(acceptable_price + 1)

            buy_volume = limit - position
            sell_volume = limit + position

            if buy_volume > 0:
                orders.append(Order(product, buy_price, buy_volume))

            if sell_volume > 0:
                orders.append(Order(product, sell_price, -sell_volume))

            return orders

        def run(self, state: TradingState):
            result = {}

            for product, order_depth in state.order_depths.items():
                acceptable_price = self.get_acceptable_price(product, order_depth)

                if acceptable_price is None:
                    result[product] = []
                    continue

                orders = self.market_make(product, acceptable_price, state)
                result[product] = orders

            traderData = ""
            conversions = 0
            return result, conversions, traderData
    


    