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

            # Best prices from current order book
            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())

            # Simple fair value estimate
            acceptable_price = (best_bid + best_ask) / 2

            print(f"{product} | best bid: {best_bid}, best ask: {best_ask}")
            print(f"{product} | acceptable price: {acceptable_price}")

            # Buy if ask is below fair value
            best_ask_amount = order_depth.sell_orders[best_ask]
            if best_ask < acceptable_price:
                print("BUY", str(-best_ask_amount) + "x", best_ask)
                orders.append(Order(product, best_ask, -best_ask_amount))

            # Sell if bid is above fair value
            best_bid_amount = order_depth.buy_orders[best_bid]
            if best_bid > acceptable_price:
                print("SELL", str(best_bid_amount) + "x", best_bid)
                orders.append(Order(product, best_bid, -best_bid_amount))

            result[product] = orders

        traderData = ""
        conversions = 0
        return result, conversions, traderData
    


    