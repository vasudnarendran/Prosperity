from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Optional, Tuple


class Trader:
    # Stable products can lean more on a known fair value.
    REFERENCE_PRICES: Dict[str, float] = {
        "EMERALDS": 10000.0,
    }

    # Minimum price edge required before we cross the spread.
    MIN_EDGE: Dict[str, float] = {
        "EMERALDS": 1.0,
        "TOMATOES": 1.0,
    }

    def get_best_bid_ask(self, order_depth: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
        return best_bid, best_ask

    def get_acceptable_price(
        self,
        product: str,
        order_depth: OrderDepth,
    ) -> Optional[float]:
        best_bid, best_ask = self.get_best_bid_ask(order_depth)
        reference_price = self.REFERENCE_PRICES.get(product)

        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2
            if reference_price is None:
                return mid_price

            # Blend the live book with a product-specific anchor.
            return (0.7 * mid_price) + (0.3 * reference_price)

        if reference_price is not None:
            return reference_price

        if best_bid is not None:
            return float(best_bid)

        if best_ask is not None:
            return float(best_ask)

        return None

    def get_trade_edge(
        self,
        product: str,
        best_bid: Optional[int],
        best_ask: Optional[int],
    ) -> float:
        min_edge = self.MIN_EDGE.get(product, 1.0)
        if best_bid is None or best_ask is None:
            return min_edge

        spread = best_ask - best_bid
        return max(min_edge, spread / 2)

    def run(self, state: TradingState):
        """Create simple aggressive orders when best prices beat fair value."""

        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))

        result = {}

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []
            best_bid, best_ask = self.get_best_bid_ask(order_depth)
            acceptable_price = self.get_acceptable_price(product, order_depth)

            print(f"Product: {product}")
            print("Acceptable price : " + str(acceptable_price))
            print(
                "Buy Order depth : "
                + str(len(order_depth.buy_orders))
                + ", Sell order depth : "
                + str(len(order_depth.sell_orders))
            )

            if acceptable_price is None:
                result[product] = orders
                continue

            trade_edge = self.get_trade_edge(product, best_bid, best_ask)
            buy_threshold = acceptable_price - trade_edge
            sell_threshold = acceptable_price + trade_edge

            if best_ask is not None:
                best_ask_amount = order_depth.sell_orders[best_ask]
                if best_ask <= buy_threshold:
                    print("BUY", str(-best_ask_amount) + "x", best_ask)
                    orders.append(Order(product, best_ask, -best_ask_amount))

            if best_bid is not None:
                best_bid_amount = order_depth.buy_orders[best_bid]
                if best_bid >= sell_threshold:
                    print("SELL", str(best_bid_amount) + "x", best_bid)
                    orders.append(Order(product, best_bid, -best_bid_amount))

            result[product] = orders

        traderData = ""
        conversions = 0
        return result, conversions, traderData
