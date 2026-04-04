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
            best_bid_amount = order_depth.buy_orders[best_bid]
            best_ask_amount = order_depth.sell_orders[best_ask]

            mid_price = (best_bid + best_ask) / 2
            position = state.position.get(product, 0)
            limit = 80

            # Fair value by product
            if product == "EMERALDS":
                acceptable_price = 10000
            else:  # TOMATOES
                acceptable_price = mid_price

            print(product, "best bid:", best_bid, "best ask:", best_ask)
            print(product, "acceptable price:", acceptable_price, "position:", position)

            # Take good asks
            if best_ask < acceptable_price and position < limit:
                buy_volume = min(-best_ask_amount, limit - position)
                if buy_volume > 0:
                    orders.append(Order(product, best_ask, buy_volume))

            # Take good bids
            if best_bid > acceptable_price and position > -limit:
                sell_volume = min(best_bid_amount, limit + position)
                if sell_volume > 0:
                    orders.append(Order(product, best_bid, -sell_volume))

            # Passive quoting around fair value
            buy_quote = int(acceptable_price - 1)
            sell_quote = int(acceptable_price + 1)

            if position < limit:
                orders.append(Order(product, buy_quote, min(5, limit - position)))

            if position > -limit:
                orders.append(Order(product, sell_quote, -min(5, limit + position)))

            result[product] = orders

        traderData = ""
        conversions = 0
        return result, conversions, traderData  