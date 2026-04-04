from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


class Trader:
    POSITION_LIMITS: Dict[str, int] = {
        "EMERALDS": 80,
        "TOMATOES": 80,
    }

    PARAMS: Dict[str, Dict[str, float]] = {
        "EMERALDS": {
            "reference_price": 10000.0,
            "reference_weight": 0.70,
            "mid_weight": 0.15,
            "micro_weight": 0.15,
            "history_weight": 0.00,
            "base_take_edge": 0.75,
            "base_quote_edge": 2.0,
            "max_quote_edge": 4.0,
            "quote_spread_divisor": 4.0,
            "inventory_skew": 0.14,
            "passive_size": 6,
            "max_take_size": 10,
            "momentum_weight": 0.00,
            "imbalance_weight": 0.00,
        },
        "TOMATOES": {
            "reference_price": 0.0,
            "reference_weight": 0.00,
            "mid_weight": 0.40,
            "micro_weight": 0.35,
            "history_weight": 0.25,
            "base_take_edge": 1.50,
            "base_quote_edge": 2.0,
            "max_quote_edge": 5.0,
            "quote_spread_divisor": 3.5,
            "inventory_skew": 0.11,
            "passive_size": 7,
            "max_take_size": 8,
            "momentum_weight": 0.18,
            "imbalance_weight": 0.75,
        },
    }

    HISTORY_LENGTH = 8
    SOFT_LIMIT_RATIO = 0.55

    def load_trader_data(self, trader_data: str) -> Dict[str, List[float]]:
        if not trader_data:
            return {}

        try:
            parsed = json.loads(trader_data)
        except json.JSONDecodeError:
            return {}

        history = parsed.get("mid_history", {})
        if not isinstance(history, dict):
            return {}

        cleaned: Dict[str, List[float]] = {}
        for product, values in history.items():
            if not isinstance(values, list):
                continue
            cleaned[product] = [float(value) for value in values[-self.HISTORY_LENGTH :]]
        return cleaned

    def build_trader_data(self, mid_history: Dict[str, List[float]]) -> str:
        return json.dumps({"mid_history": mid_history}, separators=(",", ":"))

    def get_best_prices(self, order_depth: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
        return best_bid, best_ask

    def get_top_of_book_size(self, order_depth: OrderDepth, best_bid: int, best_ask: int) -> Tuple[int, int]:
        return order_depth.buy_orders[best_bid], -order_depth.sell_orders[best_ask]

    def get_microprice(
        self,
        best_bid: int,
        best_ask: int,
        best_bid_amount: int,
        best_ask_amount: int,
    ) -> float:
        total_size = best_bid_amount + best_ask_amount
        if total_size <= 0:
            return (best_bid + best_ask) / 2

        return ((best_bid * best_ask_amount) + (best_ask * best_bid_amount)) / total_size

    def get_recent_average(self, recent_mids: List[float], fallback: float) -> float:
        if not recent_mids:
            return fallback
        return sum(recent_mids) / len(recent_mids)

    def get_market_state(
        self,
        product: str,
        best_bid: int,
        best_ask: int,
        best_bid_amount: int,
        best_ask_amount: int,
        recent_mids: List[float],
    ) -> Dict[str, float]:
        mid = (best_bid + best_ask) / 2
        micro = self.get_microprice(best_bid, best_ask, best_bid_amount, best_ask_amount)
        recent_average = self.get_recent_average(recent_mids, mid)
        spread = best_ask - best_bid
        total_size = best_bid_amount + best_ask_amount
        imbalance = 0.0
        if total_size > 0:
            imbalance = (best_bid_amount - best_ask_amount) / total_size
        momentum = mid - recent_average

        return {
            "mid": mid,
            "micro": micro,
            "recent_average": recent_average,
            "momentum": momentum,
            "imbalance": imbalance,
            "spread": float(spread),
            "best_bid": float(best_bid),
            "best_ask": float(best_ask),
        }

    def get_fair_value(self, product: str, market_state: Dict[str, float]) -> float:
        params = self.PARAMS[product]
        fair_value = 0.0

        reference_price = params["reference_price"]
        if reference_price > 0:
            fair_value += params["reference_weight"] * reference_price

        fair_value += params["mid_weight"] * market_state["mid"]
        fair_value += params["micro_weight"] * market_state["micro"]
        fair_value += params["history_weight"] * market_state["recent_average"]
        fair_value += params["momentum_weight"] * market_state["momentum"]
        fair_value += params["imbalance_weight"] * market_state["imbalance"]

        if product == "EMERALDS":
            if market_state["best_ask"] <= 10000:
                fair_value += 0.30
            if market_state["best_bid"] >= 10000:
                fair_value -= 0.30

        return fair_value

    def get_inventory_adjusted_fair_value(
        self,
        product: str,
        fair_value: float,
        position: int,
        market_state: Dict[str, float],
    ) -> float:
        adjusted = fair_value - (position * self.PARAMS[product]["inventory_skew"])

        if product == "EMERALDS":
            if market_state["best_ask"] <= 10000 and position < 0:
                adjusted += 0.40
            if market_state["best_bid"] >= 10000 and position > 0:
                adjusted -= 0.40

        return adjusted

    def get_toxicity(self, product: str, market_state: Dict[str, float]) -> float:
        if product == "EMERALDS":
            return 0.0

        toxicity = 0.0
        if abs(market_state["momentum"]) >= 2.0:
            toxicity += 0.5
        if abs(market_state["imbalance"]) >= 0.45:
            toxicity += 0.5
        return toxicity

    def get_take_edge(
        self,
        product: str,
        side: str,
        position: int,
        market_state: Dict[str, float],
    ) -> float:
        edge = self.PARAMS[product]["base_take_edge"]
        spread = market_state["spread"]

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

        if product == "TOMATOES":
            if side == "BUY":
                if market_state["momentum"] <= -2.0:
                    edge += 0.5
                elif market_state["momentum"] >= 2.0:
                    edge -= 0.25
            else:
                if market_state["momentum"] >= 2.0:
                    edge += 0.5
                elif market_state["momentum"] <= -2.0:
                    edge -= 0.25
            edge += 0.25 * self.get_toxicity(product, market_state)
        else:
            if side == "BUY" and market_state["best_ask"] <= 10000:
                edge -= 0.25
            if side == "SELL" and market_state["best_bid"] >= 10000:
                edge -= 0.25

        return max(0.5, edge)

    def get_quote_edge(
        self,
        product: str,
        position: int,
        market_state: Dict[str, float],
    ) -> float:
        params = self.PARAMS[product]
        spread = market_state["spread"]
        quote_edge = max(params["base_quote_edge"], spread / params["quote_spread_divisor"])
        quote_edge = min(params["max_quote_edge"], quote_edge)

        soft_limit = int(self.POSITION_LIMITS[product] * self.SOFT_LIMIT_RATIO)
        if abs(position) >= soft_limit:
            quote_edge += 0.5

        if product == "TOMATOES":
            quote_edge += 0.5 * self.get_toxicity(product, market_state)
        elif market_state["best_ask"] <= 10000 or market_state["best_bid"] >= 10000:
            quote_edge = max(1.5, quote_edge - 0.5)

        return min(params["max_quote_edge"], quote_edge)

    def get_passive_quotes(
        self,
        product: str,
        adjusted_fair_value: float,
        position: int,
        market_state: Dict[str, float],
    ) -> Tuple[Optional[int], Optional[int]]:
        best_bid = int(market_state["best_bid"])
        best_ask = int(market_state["best_ask"])
        quote_edge = self.get_quote_edge(product, position, market_state)

        buy_quote = math.floor(adjusted_fair_value - quote_edge)
        sell_quote = math.ceil(adjusted_fair_value + quote_edge)

        buy_quote = max(buy_quote, best_bid + 1)
        sell_quote = min(sell_quote, best_ask - 1)

        if product == "EMERALDS":
            if best_ask <= 10000 and position <= 0:
                buy_quote = min(best_ask - 1, max(best_bid + 1, buy_quote + 1))
                sell_quote = None
            elif best_bid >= 10000 and position >= 0:
                sell_quote = max(best_bid + 1, min(best_ask - 1, sell_quote - 1))
                buy_quote = None

        final_buy_quote = buy_quote if buy_quote is not None and buy_quote < best_ask else None
        final_sell_quote = sell_quote if sell_quote is not None and sell_quote > best_bid else None
        return final_buy_quote, final_sell_quote

    def should_place_passive_order(self, side: str, position: int, limit: int) -> bool:
        soft_limit = int(limit * self.SOFT_LIMIT_RATIO)
        if side == "BUY" and position >= soft_limit:
            return False
        if side == "SELL" and position <= -soft_limit:
            return False
        return True

    def get_passive_size(
        self,
        product: str,
        side: str,
        position: int,
        market_state: Dict[str, float],
    ) -> int:
        size = int(self.PARAMS[product]["passive_size"])

        if market_state["spread"] >= 14:
            size += 1

        if product == "TOMATOES":
            size -= int(self.get_toxicity(product, market_state))
        elif (
            (side == "BUY" and market_state["best_ask"] <= 10000)
            or (side == "SELL" and market_state["best_bid"] >= 10000)
        ):
            size += 1

        if side == "BUY":
            if position <= -20:
                size += 1
            elif position >= 20:
                size -= 2
        else:
            if position >= 20:
                size += 1
            elif position <= -20:
                size -= 2

        return max(1, size)

    def update_mid_history(
        self,
        mid_history: Dict[str, List[float]],
        product: str,
        mid: float,
    ) -> None:
        history = mid_history.get(product, [])
        history.append(mid)
        mid_history[product] = history[-self.HISTORY_LENGTH :]

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        mid_history = self.load_trader_data(state.traderData)

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []
            best_bid, best_ask = self.get_best_prices(order_depth)

            if product not in self.POSITION_LIMITS or best_bid is None or best_ask is None:
                result[product] = orders
                continue

            position = state.position.get(product, 0)
            limit = self.POSITION_LIMITS[product]
            buy_capacity = limit - position
            sell_capacity = limit + position
            best_bid_amount, best_ask_amount = self.get_top_of_book_size(order_depth, best_bid, best_ask)

            market_state = self.get_market_state(
                product,
                best_bid,
                best_ask,
                best_bid_amount,
                best_ask_amount,
                mid_history.get(product, []),
            )
            self.update_mid_history(mid_history, product, market_state["mid"])

            fair_value = self.get_fair_value(product, market_state)
            adjusted_fair = self.get_inventory_adjusted_fair_value(
                product,
                fair_value,
                position,
                market_state,
            )

            took_buy = False
            took_sell = False

            buy_take_edge = self.get_take_edge(product, "BUY", position, market_state)
            if best_ask <= adjusted_fair - buy_take_edge and buy_capacity > 0:
                buy_take_limit = int(self.PARAMS[product]["max_take_size"])
                if product == "EMERALDS" and best_ask <= 10000:
                    buy_take_limit += 2
                buy_volume = min(best_ask_amount, buy_take_limit, buy_capacity)
                if buy_volume > 0:
                    orders.append(Order(product, best_ask, buy_volume))
                    took_buy = True

            sell_take_edge = self.get_take_edge(product, "SELL", position, market_state)
            if best_bid >= adjusted_fair + sell_take_edge and sell_capacity > 0:
                sell_take_limit = int(self.PARAMS[product]["max_take_size"])
                if product == "EMERALDS" and best_bid >= 10000:
                    sell_take_limit += 2
                sell_volume = min(best_bid_amount, sell_take_limit, sell_capacity)
                if sell_volume > 0:
                    orders.append(Order(product, best_bid, -sell_volume))
                    took_sell = True

            buy_quote, sell_quote = self.get_passive_quotes(product, adjusted_fair, position, market_state)

            if (
                not took_buy
                and buy_quote is not None
                and buy_capacity > 0
                and self.should_place_passive_order("BUY", position, limit)
            ):
                passive_buy_size = min(
                    self.get_passive_size(product, "BUY", position, market_state),
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
                    self.get_passive_size(product, "SELL", position, market_state),
                    sell_capacity,
                )
                if passive_sell_size > 0:
                    orders.append(Order(product, sell_quote, -passive_sell_size))

            result[product] = orders

        traderData = self.build_trader_data(mid_history)
        conversions = 0
        return result, conversions, traderData
