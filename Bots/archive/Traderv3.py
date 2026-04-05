from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string

class Trader:

    def bid(self):
        return 15
    
    def run(self, state: TradingState):
        result = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []

            if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
                result[product] = orders
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())

            mid_price = (best_bid + best_ask) / 2

            # Small edge around fair value
            buy_price = int(mid_price - 1)
            sell_price = int(mid_price + 1)

            position = state.position.get(product, 0)
            limit = 80  # example position limit

            # Place passive buy
            if position < limit:
                buy_volume = limit - position
                orders.append(Order(product, buy_price, buy_volume))

            # Place passive sell
            if position > -limit:
                sell_volume = limit + position
                orders.append(Order(product, sell_price, -sell_volume))

            result[product] = orders

        traderData = ""
        conversions = 0
        return result, conversions, traderData
        


        