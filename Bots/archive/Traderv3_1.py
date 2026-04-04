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

            
            best_ask = min(order_depth.sell_orders.keys())
            best_ask_amount = order_depth.sell_orders[best_ask]

            best_bid = max(order_depth.buy_orders.keys())
            best_bid_amount = order_depth.buy_orders[best_bid]

            mid_price = (best_bid + best_ask) / 2

            # Small edge around fair value
            buy_price = int(mid_price - 1)
            sell_price = int(mid_price + 1)

            position = state.position.get(product, 0)
            limit = 80  # example position limit

            # Place passive buy
            buy_volume = min(-best_ask_amount, limit - position)
            if buy_volume > 0:
                orders.append(Order(product, buy_price, buy_volume))

            # Place passive sell
            sell_volume = min(best_bid_amount, limit + position)
            if sell_volume > 0:
                orders.append(Order(product, best_bid, -sell_volume))

            result[product] = orders

        traderData = ""
        conversions = 0
        return result, conversions, traderData
        


        