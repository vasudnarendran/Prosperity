from datamodel import OrderDepth, Order, Trade, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


DEFAULT_EMERALDS_PARAMS = {
    "REFERENCE_PRICE": 10000.0,
    "REFERENCE_WEIGHT": 0.80,
    "MID_WEIGHT": 0.20,
    "MICRO_WEIGHT": 0.00,
    "INVENTORY_SKEW": 0.12,
    "TAKE_TIER_1_DISTANCE": 1.0,
    "TAKE_TIER_2_DISTANCE": 4.0,
    "TAKE_TIER_3_DISTANCE": 8.0,
    "TAKE_TIER_1_SIZE": 6,
    "TAKE_TIER_2_SIZE": 12,
    "TAKE_TIER_3_SIZE": 20,
    "CLEAR_WIDTH": 0.0,
    "BASE_ORDER_SIZE": 10,
    "DISREGARD_EDGE": 2.0,
    "JOIN_EDGE": 1.0,
    "DEFAULT_EDGE": 8.0,
    "SOFT_LIMIT_RATIO": 0.25,
}


DEFAULT_TOMATOES_PARAMS = {
    "MID_WEIGHT": 0.25,
    "MICRO_WEIGHT": 0.30,
    "HISTORY_WEIGHT": 0.25,
    "REGRESSION_WEIGHT": 0.20,
    "RESIDUAL_REVERT_WEIGHT": 0.12,
    "IMBALANCE_WEIGHT": 0.35,
    "INVENTORY_SKEW": 0.035,
    "BASE_TAKE_EDGE": 1.25,
    "BASE_QUOTE_EDGE": 2.75,
    "MAX_QUOTE_EDGE": 5.0,
    "PASSIVE_SIZE": 8,
    "MAX_TAKE_SIZE": 10,
    "REGRESSION_WINDOW": 8,
    "REGRESSION_HORIZON": 2.0,
    "TREND_EDGE_THRESHOLD": 1.00,
    "STRONG_TREND_EDGE": 2.50,
    "FIT_THRESHOLD": 0.45,
    "TREND_IMBALANCE_THRESHOLD": 0.12,
    "TOXIC_SPREAD_THRESHOLD": 15.0,
    "TOXIC_VOLATILITY_THRESHOLD": 3.2,
    "SOFT_LIMIT_RATIO": 0.65,
    "POSITION_BIAS_DIVISOR": 12.0,
    "TREND_FAIR_BONUS": 0.25,
    "TREND_ENTRY_TAKE_BONUS": 3.0,
    "TREND_HOLD_EXIT_BONUS": 0.55,
    "STRONG_TREND_HOLD_EXIT_BONUS": 0.90,
    "TREND_PASSIVE_PUSH": 0.0,
    "TREND_PASSIVE_SIZE_BONUS": 2.0,
    "VOL_CONTROL_WINDOW": 8,
    "TIME_HORIZON_TICKS": 10000.0,
    "GAMMA_RANGE": 0.34,
    "GAMMA_TREND": 0.10,
    "GAMMA_VOLATILE": 0.40,
    "RESERVATION_SCALE": 0.12,
    "SPREAD_VOL_COEF": 0.90,
    "SPREAD_INV_COEF": 0.42,
    "SPREAD_TIME_COEF": 0.90,
    "TREND_RESERVATION_BIAS": 0.04,
    "RANGE_RESERVATION_BIAS": 0.20,
    "ALPHA_EDGE_SCALE": 1.06,
    "ALPHA_IMBALANCE_SCALE": 1.16,
    "ALPHA_THRESHOLD_SCALE": 1.03,
    "TREND_SELL_HOLD_EXTRA": 0.24,
    "TREND_BUY_TAKE_EXTRA": 0.08,
    "TREND_QUOTE_LIFT_EXTRA": 1.0,
    "HOLD_TIME_COEF": 0.08,
    "HOLD_VOL_COEF": 0.0,
    "FLOW_ML_WEIGHT": 0.22,
    "FLOW_OFI_WEIGHT": 0.18,
    "FLOW_FRONT_WEIGHT": 0.12,
    "FLOW_SHIFT_WEIGHT": 0.10,
    "FLOW_TAKE_RELIEF": 0.14,
    "STRETCH_BAD_STATE": 1.35,
    "BAD_STATE_PASSIVE_VETO": 0.10,
    "BAD_STATE_TAKER_MARGIN": 0.35,
    "BAD_STATE_QUOTE_WIDEN": 1.0,
    "QUOTE_MEMORY_TICKS": 1200,
    "MARKOUT_DELAY_TICKS": 400,
    "ADVERSE_DECAY": 0.82,
    "ADVERSE_MAX": 1.75,
    "ADVERSE_STEP": 0.28,
    "PASSIVE_MARKOUT_DECAY": 0.85,
    "PASSIVE_MARKOUT_BLOCK": -0.45,
}


class BaseProductTrader:
    HISTORY_LENGTH = 8

    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
    ) -> None:
        self.product = product
        self.state = state
        self.mid_history = mid_history
        self.position_limit = position_limit
        self.orders: List[Order] = []

        self.order_depth: Optional[OrderDepth] = state.order_depths.get(product)
        self.position = state.position.get(product, 0)
        self.buy_capacity = position_limit - self.position
        self.sell_capacity = position_limit + self.position
        self.soft_limit = int(position_limit * 0.55)

        self.buy_levels: List[Tuple[int, int]] = []
        self.sell_levels: List[Tuple[int, int]] = []
        self.best_bid: Optional[int] = None
        self.best_ask: Optional[int] = None
        self.best_bid_volume = 0
        self.best_ask_volume = 0
        self.mid: Optional[float] = None
        self.micro: Optional[float] = None
        self.spread: Optional[int] = None
        self.recent_average: Optional[float] = None
        self.momentum: float = 0.0
        self.imbalance: float = 0.0

        self._load_market_state()

    def _load_market_state(self) -> None:
        if self.order_depth is None:
            return

        self.buy_levels = sorted(
            self.order_depth.buy_orders.items(),
            key=lambda item: item[0],
            reverse=True,
        )
        self.sell_levels = sorted(
            ((price, -volume) for price, volume in self.order_depth.sell_orders.items()),
            key=lambda item: item[0],
        )

        self.best_bid = self.buy_levels[0][0] if self.buy_levels else None
        self.best_ask = self.sell_levels[0][0] if self.sell_levels else None
        if self.best_bid is None or self.best_ask is None:
            return

        self.best_bid_volume = self.buy_levels[0][1]
        self.best_ask_volume = self.sell_levels[0][1]
        self.mid = (self.best_bid + self.best_ask) / 2
        self.spread = self.best_ask - self.best_bid

        total_top_volume = self.best_bid_volume + self.best_ask_volume
        if total_top_volume > 0:
            self.micro = (
                (self.best_bid * self.best_ask_volume) + (self.best_ask * self.best_bid_volume)
            ) / total_top_volume
            self.imbalance = (self.best_bid_volume - self.best_ask_volume) / total_top_volume
        else:
            self.micro = self.mid
            self.imbalance = 0.0

        history = self.mid_history.get(self.product, [])
        self.recent_average = sum(history) / len(history) if history else self.mid
        self.momentum = self.mid - self.recent_average

        history.append(self.mid)
        self.mid_history[self.product] = history[-self.HISTORY_LENGTH :]

    def has_book(self) -> bool:
        return self.best_bid is not None and self.best_ask is not None and self.mid is not None and self.micro is not None

    def projected_position(self) -> int:
        return self.position + sum(order.quantity for order in self.orders)

    def add_buy(self, price: int, quantity: int) -> None:
        quantity = min(max(0, int(quantity)), self.buy_capacity)
        if quantity <= 0:
            return
        self.orders.append(Order(self.product, int(price), quantity))
        self.buy_capacity -= quantity

    def add_sell(self, price: int, quantity: int) -> None:
        quantity = min(max(0, int(quantity)), self.sell_capacity)
        if quantity <= 0:
            return
        self.orders.append(Order(self.product, int(price), -quantity))
        self.sell_capacity -= quantity

    def apply_parameter_overrides(
        self,
        defaults: Dict[str, float],
        overrides: Optional[Dict[str, float]],
    ) -> None:
        for key, value in defaults.items():
            setattr(self, key, value)

        if not overrides:
            return

        for key, value in overrides.items():
            if key in defaults and isinstance(value, (int, float)):
                setattr(self, key, float(value))

    def clamp_inside_spread(
        self,
        buy_quote: Optional[int],
        sell_quote: Optional[int],
    ) -> Tuple[Optional[int], Optional[int]]:
        if not self.has_book():
            return None, None

        best_bid = int(self.best_bid)
        best_ask = int(self.best_ask)

        final_buy = None
        if buy_quote is not None:
            candidate = max(int(buy_quote), best_bid + 1)
            if candidate < best_ask:
                final_buy = candidate

        final_sell = None
        if sell_quote is not None:
            candidate = min(int(sell_quote), best_ask - 1)
            if candidate > best_bid:
                final_sell = candidate

        return final_buy, final_sell

    def run(self) -> List[Order]:
        return self.orders


class EmeraldsTrader(BaseProductTrader):
    PARAMETER_DEFAULTS = DEFAULT_EMERALDS_PARAMS

    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
        params: Optional[Dict[str, float]] = None,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit)
        self.apply_parameter_overrides(self.PARAMETER_DEFAULTS, params)
        self.soft_limit = int(position_limit * self.SOFT_LIMIT_RATIO)

    def fair_value(self) -> float:
        return (
            self.REFERENCE_WEIGHT * self.REFERENCE_PRICE
            + self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
        )

    def adjusted_fair_value(self) -> float:
        return self.fair_value() - (self.projected_position() * self.INVENTORY_SKEW)

    def take_size_for_distance(self, distance: float) -> int:
        if distance >= self.TAKE_TIER_3_DISTANCE:
            return int(self.TAKE_TIER_3_SIZE)
        if distance >= self.TAKE_TIER_2_DISTANCE:
            return int(self.TAKE_TIER_2_SIZE)
        if distance >= self.TAKE_TIER_1_DISTANCE:
            return int(self.TAKE_TIER_1_SIZE)
        return 0

    def tiered_take_size(self, side: str, adjusted_fair: float) -> int:
        if side == "BUY":
            distance = adjusted_fair - float(self.best_ask)
        else:
            distance = float(self.best_bid) - adjusted_fair

        size = self.take_size_for_distance(distance)
        position = self.projected_position()

        if side == "BUY":
            if position <= -self.soft_limit:
                size += 4
            elif position >= self.soft_limit:
                size = max(0, size - 3)
        else:
            if position >= self.soft_limit:
                size += 4
            elif position <= -self.soft_limit:
                size = max(0, size - 3)

        return min(self.position_limit, size)

    def clear_orders(self, adjusted_fair: float) -> Tuple[bool, bool]:
        cleared_buy = False
        cleared_sell = False
        position = self.projected_position()

        if (
            position > 0
            and self.sell_capacity > 0
            and int(self.best_bid) >= math.ceil(adjusted_fair + self.CLEAR_WIDTH)
        ):
            before = self.sell_capacity
            quantity = min(position, self.best_bid_volume, int(self.BASE_ORDER_SIZE))
            self.add_sell(int(self.best_bid), quantity)
            cleared_sell = self.sell_capacity < before

        position = self.projected_position()
        if (
            position < 0
            and self.buy_capacity > 0
            and int(self.best_ask) <= math.floor(adjusted_fair - self.CLEAR_WIDTH)
        ):
            before = self.buy_capacity
            quantity = min(abs(position), self.best_ask_volume, int(self.BASE_ORDER_SIZE))
            self.add_buy(int(self.best_ask), quantity)
            cleared_buy = self.buy_capacity < before

        return cleared_buy, cleared_sell

    def passive_quotes(self, adjusted_fair: float) -> Tuple[Optional[int], Optional[int]]:
        asks_above_fair = [
            price for price, _volume in self.sell_levels
            if price > adjusted_fair + self.DISREGARD_EDGE
        ]
        bids_below_fair = [
            price for price, _volume in self.buy_levels
            if price < adjusted_fair - self.DISREGARD_EDGE
        ]

        buy_quote = round(adjusted_fair - self.DEFAULT_EDGE)
        sell_quote = round(adjusted_fair + self.DEFAULT_EDGE)

        best_ask_above_fair = min(asks_above_fair) if asks_above_fair else None
        best_bid_below_fair = max(bids_below_fair) if bids_below_fair else None

        if best_ask_above_fair is not None:
            if abs(best_ask_above_fair - adjusted_fair) <= self.JOIN_EDGE:
                sell_quote = best_ask_above_fair
            else:
                sell_quote = best_ask_above_fair - 1

        if best_bid_below_fair is not None:
            if abs(adjusted_fair - best_bid_below_fair) <= self.JOIN_EDGE:
                buy_quote = best_bid_below_fair
            else:
                buy_quote = best_bid_below_fair + 1

        position = self.projected_position()
        if position >= self.soft_limit:
            sell_quote -= 1
            buy_quote -= 1
        elif position <= -self.soft_limit:
            buy_quote += 1
            sell_quote += 1

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def passive_size(self, side: str) -> int:
        size = int(self.BASE_ORDER_SIZE)
        if int(self.spread) >= 16:
            size += 1

        position = self.projected_position()
        if side == "BUY":
            if position <= -self.soft_limit:
                size += 4
            elif position >= self.soft_limit:
                size = max(1, size - 6)
        else:
            if position >= self.soft_limit:
                size += 4
            elif position <= -self.soft_limit:
                size = max(1, size - 6)

        return max(1, size)

    def take_orders(self, adjusted_fair: float) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        buy_take_size = self.tiered_take_size("BUY", adjusted_fair)
        if buy_take_size > 0 and self.buy_capacity > 0:
            before = self.buy_capacity
            self.add_buy(int(self.best_ask), min(self.best_ask_volume, buy_take_size))
            took_buy = self.buy_capacity < before

        sell_take_size = self.tiered_take_size("SELL", adjusted_fair)
        if sell_take_size > 0 and self.sell_capacity > 0:
            before = self.sell_capacity
            self.add_sell(int(self.best_bid), min(self.best_bid_volume, sell_take_size))
            took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        adjusted_fair = self.adjusted_fair_value()
        took_buy, took_sell = self.take_orders(adjusted_fair)
        cleared_buy, cleared_sell = self.clear_orders(adjusted_fair)
        buy_quote, sell_quote = self.passive_quotes(adjusted_fair)
        position = self.projected_position()

        if (
            not took_buy
            and not cleared_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and position < self.soft_limit + int(self.BASE_ORDER_SIZE)
        ):
            self.add_buy(buy_quote, self.passive_size("BUY"))

        if (
            not took_sell
            and not cleared_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and position > -(self.soft_limit + int(self.BASE_ORDER_SIZE))
        ):
            self.add_sell(sell_quote, self.passive_size("SELL"))

        return self.orders


class TomatoesTrader(BaseProductTrader):
    PARAMETER_DEFAULTS = DEFAULT_TOMATOES_PARAMS

    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
        params: Optional[Dict[str, float]] = None,
        memory: Optional[Dict[str, object]] = None,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit)
        self.apply_parameter_overrides(self.PARAMETER_DEFAULTS, params)
        self.soft_limit = int(position_limit * self.SOFT_LIMIT_RATIO)
        self.memory = memory or {}
        self.resting_quotes = self.load_resting_quotes()
        self.pending_fills = self.load_pending_fills()
        self.passive_markout = self.load_passive_markout()
        self.buy_bias = float(self.memory.get("adverse_buy_bias", 0.0)) * self.ADVERSE_DECAY
        self.sell_bias = float(self.memory.get("adverse_sell_bias", 0.0)) * self.ADVERSE_DECAY
        self.last_fill_ts = int(self.memory.get("last_fill_ts", -1))
        self.next_memory: Dict[str, object] = dict(self.memory)

    def current_book_snapshot(self) -> Dict[str, List[List[int]]]:
        return {
            "buy": [[int(price), int(volume)] for price, volume in self.buy_levels[:3]],
            "sell": [[int(price), int(volume)] for price, volume in self.sell_levels[:3]],
        }

    def previous_book_snapshot(self) -> Dict[str, List[List[int]]]:
        raw = self.memory.get("book")
        if not isinstance(raw, dict):
            return {"buy": [], "sell": []}
        snapshot = {"buy": [], "sell": []}
        for side in ("buy", "sell"):
            values = raw.get(side, [])
            if isinstance(values, list):
                snapshot[side] = [
                    [int(level[0]), int(level[1])]
                    for level in values
                    if isinstance(level, list) and len(level) == 2
                ]
        return snapshot

    def load_resting_quotes(self) -> List[Dict[str, object]]:
        raw = self.memory.get("resting_quotes")
        if not isinstance(raw, list):
            return []
        quotes: List[Dict[str, object]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                quotes.append(
                    {
                        "side": str(item.get("side", "")),
                        "price": int(item.get("price", 0)),
                        "timestamp": int(item.get("timestamp", 0)),
                        "mid": float(item.get("mid", 0.0)),
                        "qty": int(item.get("qty", 0)),
                        "filled_qty": int(item.get("filled_qty", 0)),
                    }
                )
            except (TypeError, ValueError):
                continue
        return quotes[-12:]

    def load_pending_fills(self) -> List[Dict[str, float]]:
        raw = self.memory.get("pending_fills")
        if not isinstance(raw, list):
            return []
        fills: List[Dict[str, float]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                fills.append(
                    {
                        "side": str(item.get("side", "")),
                        "fill_ts": float(item.get("fill_ts", 0.0)),
                        "fill_mid": float(item.get("fill_mid", 0.0)),
                        "fill_price": float(item.get("fill_price", 0.0)),
                        "qty": float(item.get("qty", 0.0)),
                    }
                )
            except (TypeError, ValueError):
                continue
        return fills[-20:]

    def load_passive_markout(self) -> Dict[str, float]:
        raw = self.memory.get("passive_markout")
        if not isinstance(raw, dict):
            return {"BUY": 0.0, "SELL": 0.0}
        return {
            "BUY": float(raw.get("BUY", 0.0)),
            "SELL": float(raw.get("SELL", 0.0)),
        }

    def multi_level_imbalance(self) -> float:
        bid_total = 0.0
        ask_total = 0.0
        for index, (_price, volume) in enumerate(self.buy_levels[:3]):
            bid_total += volume / (index + 1)
        for index, (_price, volume) in enumerate(self.sell_levels[:3]):
            ask_total += volume / (index + 1)
        total = bid_total + ask_total
        if total <= 1e-9:
            return 0.0
        return (bid_total - ask_total) / total

    def flow_features(self, previous_book: Dict[str, List[List[int]]]) -> Tuple[float, float, float]:
        total_pressure = 0.0
        front_pressure = 0.0
        shift_pressure = 0.0

        current_book = self.current_book_snapshot()
        for side, sign in (("buy", 1.0), ("sell", -1.0)):
            prev_levels = previous_book.get(side, [])
            curr_levels = current_book.get(side, [])
            prev_map = {int(price): int(volume) for price, volume in prev_levels}
            curr_map = {int(price): int(volume) for price, volume in curr_levels}

            for index, (price, volume) in enumerate(curr_levels[:3]):
                weight = 1.0 / (index + 1)
                total_pressure += sign * weight * (volume - prev_map.get(int(price), 0))
            for index, (price, volume) in enumerate(prev_levels[:3]):
                if int(price) not in curr_map:
                    weight = 1.0 / (index + 1)
                    total_pressure -= sign * weight * volume

            prev_top_price = int(prev_levels[0][0]) if prev_levels else None
            curr_top_price = int(curr_levels[0][0]) if curr_levels else None
            prev_top_vol = int(prev_levels[0][1]) if prev_levels else 0
            curr_top_vol = int(curr_levels[0][1]) if curr_levels else 0

            front_pressure += sign * (curr_top_vol - prev_top_vol)
            if prev_top_price is not None and curr_top_price is not None:
                if side == "buy":
                    shift_pressure += 0.8 if curr_top_price > prev_top_price else (-0.8 if curr_top_price < prev_top_price else 0.0)
                else:
                    shift_pressure += 0.8 if curr_top_price > prev_top_price else (-0.8 if curr_top_price < prev_top_price else 0.0)

        return (
            max(-2.0, min(2.0, total_pressure / 30.0)),
            max(-2.0, min(2.0, front_pressure / 24.0)),
            max(-1.5, min(1.5, shift_pressure)),
        )

    def regression_metrics(self) -> Tuple[float, float, float, float]:
        history = self.mid_history.get(self.product, [])
        window = history[-int(self.REGRESSION_WINDOW) :]
        if len(window) < 2:
            return float(self.mid), float(self.mid), 0.0, 0.0

        n = len(window)
        x_mean = (n - 1) / 2.0
        y_mean = sum(window) / n
        var_x = sum((index - x_mean) ** 2 for index in range(n))
        cov_xy = sum((index - x_mean) * (price - y_mean) for index, price in enumerate(window))
        slope = cov_xy / var_x if var_x else 0.0
        intercept = y_mean - slope * x_mean

        fitted = [intercept + slope * index for index in range(n)]
        predicted_now = fitted[-1]
        predicted_next = intercept + slope * ((n - 1) + self.REGRESSION_HORIZON)

        ss_tot = sum((price - y_mean) ** 2 for price in window)
        ss_res = sum((price - fit) ** 2 for price, fit in zip(window, fitted))
        fit_quality = 0.0 if ss_tot <= 1e-9 else max(0.0, min(1.0, 1.0 - (ss_res / ss_tot)))

        diffs = [abs(window[index] - window[index - 1]) for index in range(1, n)]
        volatility = sum(diffs) / len(diffs) if diffs else 0.0
        return predicted_now, predicted_next, fit_quality, volatility

    def stretch(self, volatility: float) -> float:
        return (float(self.mid) - float(self.recent_average)) / max(1.0, volatility)

    def attribute_passive_fills(self) -> None:
        old_last_fill_ts = self.last_fill_ts
        max_seen_ts = self.last_fill_ts
        quotes = [quote.copy() for quote in self.resting_quotes]
        new_pending: List[Dict[str, float]] = []

        for trade in self.state.own_trades.get(self.product, []):
            if not isinstance(trade, Trade):
                continue
            trade_ts = int(getattr(trade, "timestamp", -1))
            if trade_ts < old_last_fill_ts:
                continue

            max_seen_ts = max(max_seen_ts, trade_ts)

            side = None
            if getattr(trade, "buyer", None) == "SUBMISSION":
                side = "BUY"
            elif getattr(trade, "seller", None) == "SUBMISSION":
                side = "SELL"
            if side is None:
                continue

            price = int(getattr(trade, "price", 0))
            remaining_trade_qty = max(1, abs(int(getattr(trade, "quantity", 0))))

            for quote in reversed(quotes):
                if remaining_trade_qty <= 0:
                    break
                if quote["side"] != side or int(quote["price"]) != price:
                    continue
                if trade_ts < int(quote["timestamp"]) or trade_ts - int(quote["timestamp"]) > int(self.QUOTE_MEMORY_TICKS):
                    continue

                remaining_quote_qty = int(quote["qty"]) - int(quote["filled_qty"])
                if remaining_quote_qty <= 0:
                    continue

                matched_qty = min(remaining_trade_qty, remaining_quote_qty)
                quote["filled_qty"] = int(quote["filled_qty"]) + matched_qty
                new_pending.append(
                    {
                        "side": side,
                        "fill_ts": float(trade_ts),
                        "fill_mid": float(self.mid),
                        "fill_price": float(price),
                        "qty": float(matched_qty),
                    }
                )
                remaining_trade_qty -= matched_qty

        trimmed_quotes: List[Dict[str, object]] = []
        for quote in quotes:
            if self.current_ts - int(quote["timestamp"]) > int(self.QUOTE_MEMORY_TICKS):
                continue
            if int(quote["filled_qty"]) >= int(quote["qty"]):
                continue
            trimmed_quotes.append(quote)

        self.last_fill_ts = max_seen_ts
        self.resting_quotes = trimmed_quotes[-12:]
        self.pending_fills.extend(new_pending)
        self.pending_fills = self.pending_fills[-20:]

    def process_matured_passive_fills(self, volatility: float) -> None:
        remaining: List[Dict[str, float]] = []
        for fill in self.pending_fills:
            age = self.current_ts - float(fill["fill_ts"])
            if age < float(self.MARKOUT_DELAY_TICKS):
                remaining.append(fill)
                continue

            side = str(fill["side"])
            side_sign = 1.0 if side == "BUY" else -1.0
            fill_mid = float(fill["fill_mid"])
            fill_price = float(fill["fill_price"])
            qty = float(fill["qty"])

            mid_markout = side_sign * (float(self.mid) - fill_mid)
            price_markout = side_sign * (float(self.mid) - fill_price)
            combined_markout = 0.30 * mid_markout + 0.70 * price_markout

            self.passive_markout[side] = (
                self.PASSIVE_MARKOUT_DECAY * self.passive_markout[side]
                + (1.0 - self.PASSIVE_MARKOUT_DECAY) * combined_markout
            )

            step = min(
                self.ADVERSE_MAX,
                self.ADVERSE_STEP * min(2.5, abs(combined_markout) / max(1.0, volatility)) * max(1.0, qty / 4.0),
            )
            if side == "BUY":
                if combined_markout < 0:
                    self.buy_bias = min(self.ADVERSE_MAX, self.buy_bias + step)
                else:
                    self.buy_bias = max(0.0, self.buy_bias - 0.5 * step)
            else:
                if combined_markout < 0:
                    self.sell_bias = min(self.ADVERSE_MAX, self.sell_bias + step)
                else:
                    self.sell_bias = max(0.0, self.sell_bias - 0.5 * step)

        self.pending_fills = remaining[-20:]

    def time_fraction_remaining(self) -> float:
        timestamp = float(getattr(self.state, "timestamp", 0))
        remaining_ticks = max(0.0, self.TIME_HORIZON_TICKS - (timestamp / 100.0))
        return remaining_ticks / self.TIME_HORIZON_TICKS

    def control_gamma(self, regime: str) -> float:
        if regime == "trend_up" or regime == "trend_down":
            return self.GAMMA_TREND
        if regime == "volatile":
            return self.GAMMA_VOLATILE
        return self.GAMMA_RANGE

    def reservation_adjustment(
        self,
        regime: str,
        target_position: int,
        predicted_edge: float,
        volatility: float,
    ) -> float:
        position = self.projected_position()
        inventory_gap = position - target_position
        gamma = self.control_gamma(regime)
        tau = self.time_fraction_remaining()
        reservation_shift = inventory_gap * gamma * max(0.6, volatility) * self.RESERVATION_SCALE * max(0.35, tau)

        if regime == "trend_up":
            reservation_shift -= self.TREND_RESERVATION_BIAS * max(0.0, predicted_edge)
        elif regime == "trend_down":
            reservation_shift += self.TREND_RESERVATION_BIAS * max(0.0, -predicted_edge)
        elif regime == "range":
            if predicted_edge > 0:
                reservation_shift -= self.RANGE_RESERVATION_BIAS * predicted_edge
            else:
                reservation_shift += self.RANGE_RESERVATION_BIAS * abs(predicted_edge)

        return reservation_shift

    def classify_state(
        self,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
        flow_alpha: float,
        stretch: float,
    ) -> str:
        trend_threshold = self.TREND_EDGE_THRESHOLD * self.ALPHA_THRESHOLD_SCALE
        if float(self.spread) >= self.TOXIC_SPREAD_THRESHOLD and volatility >= self.TOXIC_VOLATILITY_THRESHOLD:
            return "volatile"
        if (
            predicted_edge >= trend_threshold
            and fit_quality >= self.FIT_THRESHOLD
            and (self.imbalance >= self.TREND_IMBALANCE_THRESHOLD or flow_alpha >= 0.18)
            and (self.momentum >= 0.75 or flow_alpha >= 0.30)
            and float(self.micro) >= float(self.mid)
            and stretch <= 2.4
        ):
            return "trend_up"
        if (
            predicted_edge <= -trend_threshold
            and fit_quality >= self.FIT_THRESHOLD
            and (self.imbalance <= -self.TREND_IMBALANCE_THRESHOLD or flow_alpha <= -0.18)
            and (self.momentum <= -0.75 or flow_alpha <= -0.30)
            and float(self.micro) <= float(self.mid)
            and stretch >= -2.4
        ):
            return "trend_down"
        return "range"

    def target_band(self, regime: str, predicted_edge: float, fit_quality: float) -> Tuple[int, int]:
        conviction = abs(predicted_edge) * max(0.5, fit_quality)
        if regime == "trend_up":
            return (22, 44) if conviction >= self.STRONG_TREND_EDGE else (10, 28)
        if regime == "trend_down":
            return (-44, -22) if conviction >= self.STRONG_TREND_EDGE else (-28, -10)
        if regime == "volatile":
            return -6, 6
        return -14, 14

    def target_position(self, regime: str, predicted_edge: float, fit_quality: float) -> int:
        lower, upper = self.target_band(regime, predicted_edge, fit_quality)
        position = self.projected_position()
        if position < lower:
            return lower
        if position > upper:
            return upper
        if regime == "trend_up":
            return upper
        if regime == "trend_down":
            return lower
        return 0

    def toxicity(self, volatility: float) -> float:
        score = 0.0
        if volatility >= 2.0:
            score += 0.5
        if abs(self.imbalance) >= 0.45:
            score += 0.5
        return score

    def fair_value(
        self,
        regime: str,
        target_position: int,
        predicted_now: float,
        predicted_next: float,
        flow_alpha: float,
    ) -> float:
        line_gap = predicted_now - float(self.mid)
        scaled_imbalance = self.imbalance * self.ALPHA_IMBALANCE_SCALE
        fair = (
            self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
            + self.HISTORY_WEIGHT * float(self.recent_average)
            + self.REGRESSION_WEIGHT * predicted_next
            + self.IMBALANCE_WEIGHT * scaled_imbalance
        )
        fair += flow_alpha
        fair += (target_position - self.projected_position()) / self.POSITION_BIAS_DIVISOR
        if regime == "range":
            fair += self.RESIDUAL_REVERT_WEIGHT * line_gap
        else:
            fair += (0.10 * line_gap) + (self.TREND_FAIR_BONUS * (predicted_next - float(self.mid)))
        return fair

    def adjusted_fair_value(
        self,
        regime: str,
        target_position: int,
        predicted_now: float,
        predicted_next: float,
        flow_alpha: float,
    ) -> float:
        fair = self.fair_value(regime, target_position, predicted_now, predicted_next, flow_alpha)
        return fair - (self.projected_position() * self.INVENTORY_SKEW)

    def take_edge(
        self,
        side: str,
        regime: str,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
        flow_alpha: float,
    ) -> float:
        edge = self.BASE_TAKE_EDGE

        if int(self.spread) >= 14:
            edge += 0.4

        position = self.projected_position()

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

        edge += 0.20 * self.toxicity(volatility)

        if regime == "trend_up":
            if side == "BUY":
                edge += -0.35 - self.TREND_BUY_TAKE_EXTRA
            else:
                edge += 0.55 + (0.50 * self.TREND_SELL_HOLD_EXTRA)
        elif regime == "trend_down":
            if side == "SELL":
                edge += -0.35 - self.TREND_BUY_TAKE_EXTRA
            else:
                edge += 0.55 + (0.50 * self.TREND_SELL_HOLD_EXTRA)
        elif regime == "volatile":
            edge += 0.50
        else:
            if side == "BUY" and predicted_edge <= -self.TREND_EDGE_THRESHOLD:
                edge += 0.35
            if side == "SELL" and predicted_edge >= self.TREND_EDGE_THRESHOLD:
                edge += 0.35

        if predicted_edge > 0 and side == "BUY":
            edge -= min(0.20, 0.05 * predicted_edge * max(0.5, fit_quality))
        elif predicted_edge < 0 and side == "SELL":
            edge -= min(0.20, 0.05 * abs(predicted_edge) * max(0.5, fit_quality))

        if flow_alpha > 0 and side == "BUY":
            edge -= min(self.FLOW_TAKE_RELIEF, 0.10 * flow_alpha)
        elif flow_alpha < 0 and side == "SELL":
            edge -= min(self.FLOW_TAKE_RELIEF, 0.10 * abs(flow_alpha))

        return max(0.5, edge)

    def quote_edge(self, regime: str, volatility: float, fit_quality: float) -> float:
        tau = self.time_fraction_remaining()
        gamma = self.control_gamma(regime)
        edge = max(self.BASE_QUOTE_EDGE, float(self.spread) / 3.5)
        edge = min(self.MAX_QUOTE_EDGE, edge)

        if abs(self.projected_position()) >= self.soft_limit:
            edge += 0.5

        if regime == "volatile":
            edge += 1.0
        elif regime in {"trend_up", "trend_down"}:
            edge += 0.15 + (0.10 * fit_quality)

        edge += self.SPREAD_VOL_COEF * min(3.0, volatility)
        edge += self.SPREAD_INV_COEF * gamma * min(self.position_limit, abs(self.projected_position()))
        edge += self.SPREAD_TIME_COEF * gamma * tau
        return min(self.MAX_QUOTE_EDGE, edge)

    def passive_quotes(
        self,
        adjusted_fair: float,
        regime: str,
        target_position: int,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
        stretch: float,
    ) -> Tuple[Optional[int], Optional[int]]:
        buy_quote = math.floor(adjusted_fair - self.quote_edge(regime, volatility, fit_quality))
        sell_quote = math.ceil(adjusted_fair + self.quote_edge(regime, volatility, fit_quality))
        buy_quote, sell_quote = self.clamp_inside_spread(buy_quote, sell_quote)

        position = self.projected_position()
        if regime == "trend_up":
            if buy_quote is not None and position < target_position:
                buy_quote = min(
                    int(self.best_ask) - 1,
                    max(int(self.best_bid) + 1, buy_quote + int(self.TREND_PASSIVE_PUSH)),
                )
            if sell_quote is not None and position > 0:
                lift = 1 if predicted_edge >= self.TREND_EDGE_THRESHOLD else 0
                if predicted_edge >= self.STRONG_TREND_EDGE:
                    lift += 1
                lift += int(self.TREND_QUOTE_LIFT_EXTRA)
                sell_quote += lift
        elif regime == "trend_down":
            if sell_quote is not None and position > target_position:
                sell_quote = max(
                    int(self.best_bid) + 1,
                    min(int(self.best_ask) - 1, sell_quote - int(self.TREND_PASSIVE_PUSH)),
                )
            if buy_quote is not None and position < 0:
                drop = 1 if predicted_edge <= -self.TREND_EDGE_THRESHOLD else 0
                if predicted_edge <= -self.STRONG_TREND_EDGE:
                    drop += 1
                buy_quote -= drop
        elif regime == "volatile" and abs(position) <= 6:
            buy_quote = None
            sell_quote = None

        if self.is_bad_state(regime, volatility, stretch):
            if buy_quote is not None and (self.buy_bias >= 0.9 or self.passive_markout["BUY"] <= self.PASSIVE_MARKOUT_BLOCK):
                buy_quote -= int(self.BAD_STATE_QUOTE_WIDEN)
            if sell_quote is not None and (self.sell_bias >= 0.9 or self.passive_markout["SELL"] <= self.PASSIVE_MARKOUT_BLOCK):
                sell_quote += int(self.BAD_STATE_QUOTE_WIDEN)

        return self.clamp_inside_spread(buy_quote, sell_quote)

    def passive_size(self, side: str, regime: str, volatility: float) -> int:
        size = self.PASSIVE_SIZE
        if int(self.spread) >= 14:
            size += 1

        if regime == "volatile":
            size = max(1, size - 3)
        elif regime in {"trend_up", "trend_down"}:
            size = max(1, size + int(self.TREND_PASSIVE_SIZE_BONUS))

        size = max(1, int(size - self.toxicity(volatility)))

        position = self.projected_position()
        if side == "BUY":
            if position <= -20:
                size += 1
            elif position >= 20:
                size = max(1, size - 2)
        else:
            if position >= 20:
                size += 1
            elif position <= -20:
                size = max(1, size - 2)

        if side == "BUY" and (self.buy_bias >= 1.0 or self.passive_markout["BUY"] <= self.PASSIVE_MARKOUT_BLOCK):
            size = max(1, size - 2)
        if side == "SELL" and (self.sell_bias >= 1.0 or self.passive_markout["SELL"] <= self.PASSIVE_MARKOUT_BLOCK):
            size = max(1, size - 2)

        return size

    def allow_passive(self, side: str, regime: str) -> bool:
        position = self.projected_position()
        if side == "BUY" and position >= self.soft_limit:
            return False
        if side == "SELL" and position <= -self.soft_limit:
            return False
        if regime == "volatile" and abs(position) <= 6:
            return False
        return True

    def side_inventory_help(self, side: str, target_position: int) -> bool:
        position = self.projected_position()
        if side == "BUY":
            return position < target_position
        return position > target_position

    def is_bad_state(self, regime: str, volatility: float, stretch: float) -> bool:
        return (
            regime == "volatile"
            or abs(stretch) >= self.STRETCH_BAD_STATE
            or self.toxicity(volatility) >= 0.75
        )

    def passive_expected_value(
        self,
        side: str,
        quote: int,
        adjusted_fair: float,
        regime: str,
        volatility: float,
        stretch: float,
        target_position: int,
    ) -> float:
        spread_capture = (adjusted_fair - quote) if side == "BUY" else (quote - adjusted_fair)
        bias = self.buy_bias if side == "BUY" else self.sell_bias
        markout = self.passive_markout[side]
        inventory_help = self.side_inventory_help(side, target_position)

        adverse_cost = 0.12
        adverse_cost += 0.18 * self.toxicity(volatility)
        adverse_cost += 0.14 * max(0.0, abs(stretch) - 1.0)
        adverse_cost += 0.20 * bias
        adverse_cost += 0.22 * max(0.0, -markout)

        if inventory_help:
            adverse_cost -= 0.08
        if regime == "volatile":
            adverse_cost += 0.18

        return spread_capture - adverse_cost

    def should_veto_passive(
        self,
        side: str,
        ev: float,
        regime: str,
        volatility: float,
        stretch: float,
        target_position: int,
    ) -> bool:
        if not self.is_bad_state(regime, volatility, stretch):
            return False

        bias = self.buy_bias if side == "BUY" else self.sell_bias
        markout = self.passive_markout[side]
        inventory_help = self.side_inventory_help(side, target_position)

        if ev < self.BAD_STATE_PASSIVE_VETO and not inventory_help:
            return True
        if markout <= self.PASSIVE_MARKOUT_BLOCK and not inventory_help:
            return True
        if bias >= 1.2 and regime == "volatile":
            return True
        return False

    def should_veto_take(
        self,
        side: str,
        regime: str,
        predicted_edge: float,
        volatility: float,
        stretch: float,
        take_margin: float,
    ) -> bool:
        if not self.is_bad_state(regime, volatility, stretch):
            return False

        aligned_trend = (
            (regime == "trend_up" and side == "BUY")
            or (regime == "trend_down" and side == "SELL")
        )
        if aligned_trend and abs(predicted_edge) >= self.STRONG_TREND_EDGE:
            return False

        required_margin = self.BAD_STATE_TAKER_MARGIN
        if regime == "range":
            required_margin += 0.10
        if not aligned_trend:
            required_margin += 0.12

        return take_margin < required_margin

    def take_orders(
        self,
        regime: str,
        target_position: int,
        adjusted_fair: float,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
        stretch: float,
        flow_alpha: float,
    ) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        buy_edge_threshold = self.take_edge("BUY", regime, predicted_edge, fit_quality, volatility, flow_alpha)
        if (
            int(self.best_ask) <= adjusted_fair - buy_edge_threshold
            and self.buy_capacity > 0
        ):
            take_margin = adjusted_fair - int(self.best_ask) - buy_edge_threshold
            take_limit = self.MAX_TAKE_SIZE + (int(self.TREND_ENTRY_TAKE_BONUS) if regime == "trend_up" else 0)
            if regime != "range" and self.projected_position() >= target_position:
                pass
            elif self.should_veto_take("BUY", regime, predicted_edge, volatility, stretch, take_margin):
                pass
            else:
                quantity = min(self.best_ask_volume, take_limit)
                if regime != "range":
                    quantity = min(quantity, max(1, target_position - self.projected_position()))
                before = self.buy_capacity
                self.add_buy(int(self.best_ask), quantity)
                took_buy = self.buy_capacity < before

        sell_edge_threshold = self.take_edge("SELL", regime, predicted_edge, fit_quality, volatility, flow_alpha)
        if (
            int(self.best_bid) >= adjusted_fair + sell_edge_threshold
            and self.sell_capacity > 0
        ):
            take_limit = self.MAX_TAKE_SIZE + (int(self.TREND_ENTRY_TAKE_BONUS) if regime == "trend_down" else 0)
            required_bonus = 0.0
            if regime == "trend_up" and predicted_edge >= self.TREND_EDGE_THRESHOLD:
                required_bonus += self.TREND_HOLD_EXIT_BONUS + self.TREND_SELL_HOLD_EXTRA
            if regime == "trend_up" and predicted_edge >= self.STRONG_TREND_EDGE:
                required_bonus += self.STRONG_TREND_HOLD_EXIT_BONUS + self.TREND_SELL_HOLD_EXTRA
            required_bonus += self.HOLD_TIME_COEF * self.time_fraction_remaining()
            required_bonus += self.HOLD_VOL_COEF * min(3.0, volatility)
            take_margin = int(self.best_bid) - adjusted_fair - sell_edge_threshold
            if regime != "range" and self.projected_position() <= target_position:
                pass
            elif int(self.best_bid) < adjusted_fair + sell_edge_threshold + required_bonus:
                pass
            elif self.should_veto_take("SELL", regime, predicted_edge, volatility, stretch, take_margin):
                pass
            else:
                quantity = min(self.best_bid_volume, take_limit)
                if regime != "range":
                    quantity = min(quantity, max(1, self.projected_position() - target_position))
                before = self.sell_capacity
                self.add_sell(int(self.best_bid), quantity)
                took_sell = self.sell_capacity < before

        return took_buy, took_sell

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        self.current_ts = int(getattr(self.state, "timestamp", 0))
        self.attribute_passive_fills()
        predicted_now, predicted_next, fit_quality, volatility = self.regression_metrics()
        previous_book = self.previous_book_snapshot()
        ml_imbalance = self.multi_level_imbalance()
        total_flow, front_flow, shift_flow = self.flow_features(previous_book)
        flow_alpha = (
            self.FLOW_ML_WEIGHT * ml_imbalance
            + self.FLOW_OFI_WEIGHT * total_flow
            + self.FLOW_FRONT_WEIGHT * front_flow
            + self.FLOW_SHIFT_WEIGHT * shift_flow
        )
        predicted_edge = (predicted_next - float(self.mid)) * self.ALPHA_EDGE_SCALE + flow_alpha
        predicted_next = float(self.mid) + predicted_edge
        stretch = self.stretch(volatility)
        regime = self.classify_state(predicted_edge, fit_quality, volatility, flow_alpha, stretch)
        target_position = self.target_position(regime, predicted_edge, fit_quality)
        self.process_matured_passive_fills(volatility)
        adjusted_fair = self.adjusted_fair_value(
            regime,
            target_position,
            predicted_now,
            predicted_next,
            flow_alpha,
        ) - self.reservation_adjustment(regime, target_position, predicted_edge, volatility)
        took_buy, took_sell = self.take_orders(
            regime,
            target_position,
            adjusted_fair,
            predicted_edge,
            fit_quality,
            volatility,
            stretch,
            flow_alpha,
        )

        buy_quote, sell_quote = self.passive_quotes(
            adjusted_fair,
            regime,
            target_position,
            predicted_edge,
            fit_quality,
            volatility,
            stretch,
        )
        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.allow_passive("BUY", regime)
        ):
            if regime == "range" or position < target_position:
                buy_ev = self.passive_expected_value(
                    "BUY",
                    int(buy_quote),
                    adjusted_fair,
                    regime,
                    volatility,
                    stretch,
                    target_position,
                )
                if self.should_veto_passive("BUY", buy_ev, regime, volatility, stretch, target_position):
                    buy_quote = None
            if buy_quote is not None and (regime == "range" or position < target_position):
                quantity = min(self.passive_size("BUY", regime, volatility), self.buy_capacity)
                if regime != "range":
                    quantity = min(quantity, max(1, target_position - position))
                self.add_buy(buy_quote, quantity)
                self.resting_quotes.append(
                    {
                        "side": "BUY",
                        "price": int(buy_quote),
                        "timestamp": self.current_ts,
                        "mid": float(self.mid),
                        "qty": int(quantity),
                        "filled_qty": 0,
                    }
                )

        position = self.projected_position()
        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.allow_passive("SELL", regime)
        ):
            if regime == "range" or position > target_position:
                sell_ev = self.passive_expected_value(
                    "SELL",
                    int(sell_quote),
                    adjusted_fair,
                    regime,
                    volatility,
                    stretch,
                    target_position,
                )
                if self.should_veto_passive("SELL", sell_ev, regime, volatility, stretch, target_position):
                    sell_quote = None
            if sell_quote is not None and (regime == "range" or position > target_position):
                quantity = min(self.passive_size("SELL", regime, volatility), self.sell_capacity)
                if regime != "range":
                    quantity = min(quantity, max(1, position - target_position))
                self.add_sell(sell_quote, quantity)
                self.resting_quotes.append(
                    {
                        "side": "SELL",
                        "price": int(sell_quote),
                        "timestamp": self.current_ts,
                        "mid": float(self.mid),
                        "qty": int(quantity),
                        "filled_qty": 0,
                    }
                )

        self.next_memory = {
            "book": self.current_book_snapshot(),
            "resting_quotes": self.resting_quotes[-12:],
            "pending_fills": self.pending_fills[-20:],
            "passive_markout": self.passive_markout,
            "adverse_buy_bias": self.buy_bias,
            "adverse_sell_bias": self.sell_bias,
            "last_fill_ts": self.last_fill_ts,
        }

        return self.orders


class Trader:
    POSITION_LIMITS: Dict[str, int] = {
        "EMERALDS": 80,
        "TOMATOES": 80,
    }

    PRODUCT_TRADERS = {
        "EMERALDS": EmeraldsTrader,
        "TOMATOES": TomatoesTrader,
    }

    def load_trader_data(self, trader_data: str) -> Tuple[Dict[str, List[float]], Dict[str, Dict[str, object]]]:
        if not trader_data:
            return {}, {}
        try:
            parsed = json.loads(trader_data)
        except json.JSONDecodeError:
            return {}, {}

        raw_history = parsed.get("mid_history", {})
        cleaned: Dict[str, List[float]] = {}
        if isinstance(raw_history, dict):
            for product, values in raw_history.items():
                if isinstance(values, list):
                    cleaned[product] = [float(value) for value in values[-BaseProductTrader.HISTORY_LENGTH :]]

        raw_memory = parsed.get("memory", {})
        memory: Dict[str, Dict[str, object]] = {}
        if isinstance(raw_memory, dict):
            for product, values in raw_memory.items():
                if isinstance(values, dict):
                    memory[product] = values
        return cleaned, memory

    def build_trader_data(self, mid_history: Dict[str, List[float]], memory: Dict[str, Dict[str, object]]) -> str:
        return json.dumps({"mid_history": mid_history, "memory": memory}, separators=(",", ":"))

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        mid_history, memory = self.load_trader_data(state.traderData)
        next_memory: Dict[str, Dict[str, object]] = dict(memory)

        for product in state.order_depths:
            if product not in self.PRODUCT_TRADERS:
                result[product] = []
                continue

            trader_class = self.PRODUCT_TRADERS[product]
            if product == "TOMATOES":
                trader = trader_class(
                    product,
                    state,
                    mid_history,
                    self.POSITION_LIMITS[product],
                    memory=memory.get(product, {}),
                )
                result[product] = trader.run()
                next_memory[product] = trader.next_memory
            else:
                trader = trader_class(
                    product,
                    state,
                    mid_history,
                    self.POSITION_LIMITS[product],
                )
                result[product] = trader.run()

        conversions = 0
        trader_data = self.build_trader_data(mid_history, next_memory)
        return result, conversions, trader_data
