from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


class Trader:
    POSITION_LIMITS: Dict[str, int] = {
        "EMERALDS": 80,
        "TOMATOES": 80,
    }

    HISTORY_LENGTH = 12

    PRODUCT_PARAMS: Dict[str, Dict[str, float]] = {
        "EMERALDS": {
            "reference_price": 10000.0,
            "inventory_skew": 0.14,
            "base_take_edge": 0.8,
            "base_quote_edge": 2.0,
            "max_quote_edge": 4.0,
            "quote_spread_divisor": 4.0,
            "max_take_size": 10,
            "passive_size": 7,
            "target_scale": 8.0,
            "target_cap": 36.0,
            "volatility_soft_cap": 24.0,
        },
        "TOMATOES": {
            "inventory_skew": 0.10,
            "base_take_edge": 1.25,
            "base_quote_edge": 2.0,
            "max_quote_edge": 5.0,
            "quote_spread_divisor": 3.5,
            "max_take_size": 8,
            "passive_size": 7,
            "target_scale": 11.0,
            "target_cap": 44.0,
            "volatility_soft_cap": 24.0,
        },
    }

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

    def update_mid_history(
        self,
        mid_history: Dict[str, List[float]],
        product: str,
        mid: float,
    ) -> None:
        history = mid_history.get(product, [])
        history.append(mid)
        mid_history[product] = history[-self.HISTORY_LENGTH :]

    def get_best_prices(self, order_depth: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
        return best_bid, best_ask

    def get_top_of_book_size(
        self,
        order_depth: OrderDepth,
        best_bid: int,
        best_ask: int,
    ) -> Tuple[int, int]:
        return order_depth.buy_orders[best_bid], -order_depth.sell_orders[best_ask]

    def get_average(self, values: List[float], fallback: float, length: int) -> float:
        if not values:
            return fallback
        window = values[-length:]
        return sum(window) / len(window)

    def get_realized_volatility(self, recent_mids: List[float], current_mid: float) -> float:
        series = recent_mids[-5:] + [current_mid]
        if len(series) < 2:
            return 0.0

        diffs = [abs(series[i] - series[i - 1]) for i in range(1, len(series))]
        return sum(diffs) / len(diffs)

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

    def get_market_state(
        self,
        best_bid: int,
        best_ask: int,
        best_bid_amount: int,
        best_ask_amount: int,
        recent_mids: List[float],
    ) -> Dict[str, float]:
        mid = (best_bid + best_ask) / 2
        micro = self.get_microprice(best_bid, best_ask, best_bid_amount, best_ask_amount)
        short_average = self.get_average(recent_mids, mid, 3)
        long_average = self.get_average(recent_mids, mid, 8)
        total_size = best_bid_amount + best_ask_amount
        imbalance = 0.0
        if total_size > 0:
            imbalance = (best_bid_amount - best_ask_amount) / total_size

        return {
            "mid": mid,
            "micro": micro,
            "short_average": short_average,
            "long_average": long_average,
            "short_momentum": mid - short_average,
            "long_momentum": mid - long_average,
            "spread": float(best_ask - best_bid),
            "imbalance": imbalance,
            "volatility": self.get_realized_volatility(recent_mids, mid),
            "best_bid": float(best_bid),
            "best_ask": float(best_ask),
        }

    def classify_regime(self, product: str, market_state: Dict[str, float]) -> str:
        if product == "EMERALDS":
            if market_state["best_ask"] <= 10000:
                return "cheap"
            if market_state["best_bid"] >= 10000:
                return "rich"
            return "anchor"

        if market_state["volatility"] >= 3.5 or market_state["spread"] >= 15:
            return "volatile"
        if market_state["long_momentum"] >= 2.0 and market_state["imbalance"] >= 0.10:
            return "trend_up"
        if market_state["long_momentum"] <= -2.0 and market_state["imbalance"] <= -0.10:
            return "trend_down"
        return "mean_revert"

    def get_alpha(
        self,
        product: str,
        regime: str,
        market_state: Dict[str, float],
    ) -> float:
        mid = market_state["mid"]
        micro_dislocation = market_state["micro"] - mid

        if product == "EMERALDS":
            anchor_gap = 10000.0 - mid
            alpha = 0.90 * anchor_gap + 0.35 * micro_dislocation
            if regime == "cheap":
                alpha += 0.80
            elif regime == "rich":
                alpha -= 0.80
            return alpha

        trend_signal = 0.65 * market_state["long_momentum"] + 0.35 * market_state["short_momentum"]
        mean_reversion_signal = -(mid - market_state["long_average"])
        flow_signal = 1.20 * micro_dislocation + 0.80 * market_state["imbalance"]

        if regime == "trend_up":
            return 0.85 * trend_signal + 0.45 * flow_signal
        if regime == "trend_down":
            return 0.85 * trend_signal + 0.45 * flow_signal
        if regime == "volatile":
            return 0.40 * trend_signal + 0.60 * flow_signal
        return 0.70 * mean_reversion_signal + 0.55 * flow_signal

    def get_target_position(
        self,
        product: str,
        regime: str,
        alpha: float,
        market_state: Dict[str, float],
    ) -> int:
        params = self.PRODUCT_PARAMS[product]
        limit = self.POSITION_LIMITS[product]

        target = alpha * params["target_scale"]
        cap = params["target_cap"]

        if regime == "volatile":
            cap = min(cap, params["volatility_soft_cap"])
        elif product == "EMERALDS" and regime in {"cheap", "rich"}:
            cap = min(limit, cap + 8)

        target = max(-cap, min(cap, target))
        target = max(-limit, min(limit, target))
        return int(round(target))

    def get_reservation_price(
        self,
        product: str,
        position: int,
        target_position: int,
        market_state: Dict[str, float],
    ) -> float:
        params = self.PRODUCT_PARAMS[product]
        fair_value = market_state["mid"] + (target_position / params["target_scale"])
        reservation_price = fair_value - (position * params["inventory_skew"])

        if product == "EMERALDS":
            if market_state["best_ask"] <= 10000 and target_position > position:
                reservation_price += 0.30
            if market_state["best_bid"] >= 10000 and target_position < position:
                reservation_price -= 0.30

        return reservation_price

    def should_pause_passive_trading(
        self,
        product: str,
        regime: str,
        alpha: float,
        market_state: Dict[str, float],
    ) -> bool:
        if product == "TOMATOES" and regime == "volatile" and abs(alpha) < 1.25:
            return True
        return False

    def get_take_edge(
        self,
        product: str,
        side: str,
        position: int,
        target_position: int,
        regime: str,
        market_state: Dict[str, float],
    ) -> float:
        edge = self.PRODUCT_PARAMS[product]["base_take_edge"]

        if market_state["spread"] >= 14:
            edge += 0.5
        if abs(target_position - position) >= 20:
            edge -= 0.25

        if product == "TOMATOES":
            if regime == "trend_up":
                if side == "BUY":
                    edge -= 0.25
                else:
                    edge += 0.35
            elif regime == "trend_down":
                if side == "SELL":
                    edge -= 0.25
                else:
                    edge += 0.35
            elif regime == "volatile":
                edge += 0.35
        else:
            if regime == "cheap" and side == "BUY":
                edge -= 0.20
            if regime == "rich" and side == "SELL":
                edge -= 0.20

        return max(0.5, edge)

    def get_quote_edge(
        self,
        product: str,
        regime: str,
        market_state: Dict[str, float],
    ) -> float:
        params = self.PRODUCT_PARAMS[product]
        quote_edge = max(
            params["base_quote_edge"],
            market_state["spread"] / params["quote_spread_divisor"],
        )

        if product == "TOMATOES":
            if regime == "volatile":
                quote_edge += 0.75
            elif regime in {"trend_up", "trend_down"}:
                quote_edge += 0.25
        elif regime in {"cheap", "rich"}:
            quote_edge = max(1.5, quote_edge - 0.5)

        return min(params["max_quote_edge"], quote_edge)

    def get_passive_quotes(
        self,
        product: str,
        position: int,
        target_position: int,
        reservation_price: float,
        regime: str,
        market_state: Dict[str, float],
    ) -> Tuple[Optional[int], Optional[int]]:
        best_bid = int(market_state["best_bid"])
        best_ask = int(market_state["best_ask"])
        quote_edge = self.get_quote_edge(product, regime, market_state)

        buy_quote = max(best_bid + 1, math.floor(reservation_price - quote_edge))
        sell_quote = min(best_ask - 1, math.ceil(reservation_price + quote_edge))

        if target_position - position >= 10:
            buy_quote = min(best_ask - 1, buy_quote + 1)
        elif position - target_position >= 10:
            sell_quote = max(best_bid + 1, sell_quote - 1)

        if product == "TOMATOES":
            if regime == "trend_up" and target_position > position:
                sell_quote = None
            elif regime == "trend_down" and target_position < position:
                buy_quote = None
        elif product == "EMERALDS":
            if regime == "cheap" and target_position >= position:
                sell_quote = None
            elif regime == "rich" and target_position <= position:
                buy_quote = None

        final_buy = buy_quote if buy_quote is not None and buy_quote < best_ask else None
        final_sell = sell_quote if sell_quote is not None and sell_quote > best_bid else None
        return final_buy, final_sell

    def get_passive_size(
        self,
        product: str,
        side: str,
        position: int,
        target_position: int,
        regime: str,
        market_state: Dict[str, float],
    ) -> int:
        size = int(self.PRODUCT_PARAMS[product]["passive_size"])

        distance_to_target = abs(target_position - position)
        if distance_to_target >= 20:
            size += 1

        if market_state["spread"] >= 14:
            size += 1

        if product == "TOMATOES" and regime == "volatile":
            size -= 2
        if product == "EMERALDS" and regime in {"cheap", "rich"}:
            size += 1

        if side == "BUY" and target_position <= position:
            size -= 1
        if side == "SELL" and target_position >= position:
            size -= 1

        return max(1, size)

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
                best_bid,
                best_ask,
                best_bid_amount,
                best_ask_amount,
                mid_history.get(product, []),
            )
            self.update_mid_history(mid_history, product, market_state["mid"])

            regime = self.classify_regime(product, market_state)
            alpha = self.get_alpha(product, regime, market_state)
            target_position = self.get_target_position(product, regime, alpha, market_state)
            reservation_price = self.get_reservation_price(
                product,
                position,
                target_position,
                market_state,
            )

            took_buy = False
            took_sell = False

            position_gap = target_position - position

            if position_gap > 0 and buy_capacity > 0:
                buy_take_edge = self.get_take_edge(
                    product,
                    "BUY",
                    position,
                    target_position,
                    regime,
                    market_state,
                )
                if best_ask <= reservation_price - buy_take_edge:
                    buy_volume = min(
                        best_ask_amount,
                        int(self.PRODUCT_PARAMS[product]["max_take_size"]),
                        buy_capacity,
                        max(1, position_gap),
                    )
                    if buy_volume > 0:
                        orders.append(Order(product, best_ask, buy_volume))
                        took_buy = True
                        position_gap -= buy_volume

            if position_gap < 0 and sell_capacity > 0:
                sell_take_edge = self.get_take_edge(
                    product,
                    "SELL",
                    position,
                    target_position,
                    regime,
                    market_state,
                )
                if best_bid >= reservation_price + sell_take_edge:
                    sell_volume = min(
                        best_bid_amount,
                        int(self.PRODUCT_PARAMS[product]["max_take_size"]),
                        sell_capacity,
                        max(1, -position_gap),
                    )
                    if sell_volume > 0:
                        orders.append(Order(product, best_bid, -sell_volume))
                        took_sell = True

            if self.should_pause_passive_trading(product, regime, alpha, market_state):
                result[product] = orders
                continue

            buy_quote, sell_quote = self.get_passive_quotes(
                product,
                position,
                target_position,
                reservation_price,
                regime,
                market_state,
            )

            if (
                buy_quote is not None
                and not took_buy
                and buy_capacity > 0
                and target_position > position
            ):
                passive_buy_size = min(
                    self.get_passive_size(
                        product,
                        "BUY",
                        position,
                        target_position,
                        regime,
                        market_state,
                    ),
                    buy_capacity,
                    max(1, target_position - position),
                )
                if passive_buy_size > 0:
                    orders.append(Order(product, buy_quote, passive_buy_size))

            if (
                sell_quote is not None
                and not took_sell
                and sell_capacity > 0
                and target_position < position
            ):
                passive_sell_size = min(
                    self.get_passive_size(
                        product,
                        "SELL",
                        position,
                        target_position,
                        regime,
                        market_state,
                    ),
                    sell_capacity,
                    max(1, position - target_position),
                )
                if passive_sell_size > 0:
                    orders.append(Order(product, sell_quote, -passive_sell_size))

            result[product] = orders

        traderData = self.build_trader_data(mid_history)
        conversions = 0
        return result, conversions, traderData
