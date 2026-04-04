from datamodel import OrderDepth, Order, TradingState
from typing import List, Optional, Tuple


class Trader:
    POSITION_LIMIT = 80
    PASSIVE_ORDER_SIZE = 5
    MAX_TAKE_SIZE = 10

    def get_best_prices(self, order_depth: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
        return best_bid, best_ask

    def get_base_prices(self, best_bid: int, best_ask: int) -> Tuple[int, int]:
        mid_price = (best_bid + best_ask) / 2
        buy_price = int(mid_price - 1)
        sell_price = int(mid_price + 1)
        return buy_price, sell_price

    def get_quote_prices(
        self,
        best_bid: int,
        best_ask: int,
        buy_price: int,
        sell_price: int,
    ) -> Tuple[Optional[int], Optional[int]]:
        spread = best_ask - best_bid

        if spread > 2:
            buy_quote = max(buy_price, best_bid + 1)
            sell_quote = min(sell_price, best_ask - 1)
        else:
            buy_quote = buy_price
            sell_quote = sell_price

        if buy_quote >= best_ask:
            buy_quote = None

        if sell_quote <= best_bid:
            sell_quote = None

        return buy_quote, sell_quote

    def run(self, state: TradingState):
        result = {}

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []
            best_bid, best_ask = self.get_best_prices(order_depth)

            if best_bid is None or best_ask is None:
                result[product] = orders
                continue

            best_bid_amount = order_depth.buy_orders[best_bid]
            best_ask_amount = -order_depth.sell_orders[best_ask]
            buy_price, sell_price = self.get_base_prices(best_bid, best_ask)
            buy_quote, sell_quote = self.get_quote_prices(best_bid, best_ask, buy_price, sell_price)

            position = state.position.get(product, 0)
            buy_capacity = self.POSITION_LIMIT - position
            sell_capacity = self.POSITION_LIMIT + position

            # If the visible ask is already better than our fair buy level, take it.
            if best_ask <= buy_price and buy_capacity > 0:
                buy_volume = min(best_ask_amount, self.MAX_TAKE_SIZE, buy_capacity)
                if buy_volume > 0:
                    orders.append(Order(product, best_ask, buy_volume))
            elif buy_quote is not None and buy_capacity > 0:
                buy_volume = min(self.PASSIVE_ORDER_SIZE, buy_capacity)
                if buy_volume > 0:
                    orders.append(Order(product, buy_quote, buy_volume))

            # If the visible bid is already better than our fair sell level, take it.
            if best_bid >= sell_price and sell_capacity > 0:
                sell_volume = min(best_bid_amount, self.MAX_TAKE_SIZE, sell_capacity)
                if sell_volume > 0:
                    orders.append(Order(product, best_bid, -sell_volume))
            elif sell_quote is not None and sell_capacity > 0:
                sell_volume = min(self.PASSIVE_ORDER_SIZE, sell_capacity)
                if sell_volume > 0:
                    orders.append(Order(product, sell_quote, -sell_volume))

            result[product] = orders

        traderData = ""
        conversions = 0
        return result, conversions, traderData
