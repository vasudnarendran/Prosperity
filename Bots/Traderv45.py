from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


DEFAULT_EMERALDS_PARAMS = {
    "REFERENCE_PRICE": 10000.0,
    "REFERENCE_WEIGHT": 0.80,
    "MID_WEIGHT": 0.20,
    "MICRO_WEIGHT": 0.00,
    "INVENTORY_SKEW": 0.0328922991,
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
    "SOFT_LIMIT_RATIO": 0.6357999832,
}


DEFAULT_TOMATOES_PARAMS = {
    "MID_WEIGHT": 0.25,
    "MICRO_WEIGHT": 0.30,
    "HISTORY_WEIGHT": 0.25,
    "REGRESSION_WEIGHT": 0.20,
    "RESIDUAL_REVERT_WEIGHT": 0.12,
    "IMBALANCE_WEIGHT": 0.35,
    "INVENTORY_SKEW": 0.005,
    "BASE_TAKE_EDGE": 0.78,
    "BASE_QUOTE_EDGE": 2.68,
    "MAX_QUOTE_EDGE": 9.0,
    "PASSIVE_SIZE": 8,
    "MAX_TAKE_SIZE": 10,
    "REGRESSION_WINDOW": 8,
    "REGRESSION_HORIZON": 0.5,
    "TREND_EDGE_THRESHOLD": 1.00,
    "STRONG_TREND_EDGE": 2.50,
    "FIT_THRESHOLD": 0.45,
    "TREND_IMBALANCE_THRESHOLD": 0.12,
    "TOXIC_SPREAD_THRESHOLD": 15.0,
    "TOXIC_VOLATILITY_THRESHOLD": 3.2,
    "SOFT_LIMIT_RATIO": 0.56828726,
    "POSITION_BIAS_DIVISOR": 12.0,
    "TREND_FAIR_BONUS": 0.25,
    "TREND_ENTRY_TAKE_BONUS": 3.0,
    "TREND_HOLD_EXIT_BONUS": 0.55,
    "STRONG_TREND_HOLD_EXIT_BONUS": 0.90,
    "TREND_PASSIVE_PUSH": 0.0,
    "TREND_PASSIVE_SIZE_BONUS": 2.0,
    "VOL_CONTROL_WINDOW": 8,
    "TIME_HORIZON_TICKS": 10000.0,
    "GAMMA_RANGE": 0.69283327,
    "GAMMA_TREND": 0.10,
    "GAMMA_VOLATILE": 0.40,
    "RESERVATION_SCALE": 0.02,
    "SPREAD_VOL_COEF": 0.1,
    "SPREAD_INV_COEF": 1.1081637,
    "SPREAD_TIME_COEF": 1.7791177,
    "TREND_RESERVATION_BIAS": 0.04,
    "RANGE_RESERVATION_BIAS": 0.26486122,
    "ALPHA_EDGE_SCALE": 1.4153631,
    "ALPHA_IMBALANCE_SCALE": 0.7,
    "ALPHA_THRESHOLD_SCALE": 1.03,
    "TREND_SELL_HOLD_EXTRA": 0.24,
    "TREND_BUY_TAKE_EXTRA": 0.08,
    "TREND_QUOTE_LIFT_EXTRA": 1.0,
    "HOLD_TIME_COEF": 0.08,
    "HOLD_VOL_COEF": 0.0,
    "ALPHA_REFERENCE_WEIGHT": 0.45,
    "ALPHA_MID_WEIGHT": 0.20,
    "ALPHA_MICRO_WEIGHT": 0.25,
    "ALPHA_FLOW_WEIGHT": 0.10,
    "ALPHA_FLOW_SPREAD_SCALE": 0.50,
    "ALPHA_BLEND_WEIGHT": 0.28,
    "FAIR_ALPHA_WEIGHT": 0.42,
    "ALPHA_CAP": 2.20,
    "RANGE_ALPHA_DAMP": 0.35,
    "CONFLICT_ALPHA_DAMP": 0.45,
    "MOMENTUM_ALPHA_DAMP": 0.70,
    "POSITION_ALPHA_DAMP_START": 14.0,
    "POSITION_ALPHA_DAMP_END": 28.0,
    "MOMENTUM_TREND_THRESHOLD": 0.75,
    "FLOW_SHORT_WINDOW": 6,
    "FLOW_LONG_WINDOW": 18,
    "BURST_PERCENTILE": 0.88,
    "BURST_CONFIRM_IMBALANCE": 0.10,
    "PRESSURE_MEMORY_DECAY": 0.82,
    "PRESSURE_PRICE_BUCKET": 2.0,
    "PRESSURE_BIAS_SCALE": 0.22,
    "BREAKOUT_FOLLOW_SCALE": 0.18,
    "BREAKOUT_QUOTE_TIGHTEN": 0.28,
    "BREAKOUT_HOLD_BONUS": 0.12,
    "BOOK_ACTIVITY_FLOOR": 0.60,
    "BOOK_STEP_WEIGHT": 0.85,
    "BOOK_DEPLETION_WEIGHT": 0.65,
    "BOOK_REBUILD_WEIGHT": 0.25,
    "MICRO_DRIFT_WEIGHT": 0.55,
    "MID_DRIFT_WEIGHT": 0.25,
    "SPREAD_COMPRESSION_WEIGHT": 0.35,
    "PERSISTENCE_WEIGHT": 0.35,
    "DEPTH_LEVELS_SHORT": 3,
    "DEPTH_LEVELS_LONG": 5,
    "DEPTH_ALPHA_WEIGHT": 0.10,
    "CHANNEL_WINDOW": 18,
    "CHANNEL_POSITION_WEIGHT": 0.08,
    "CHANNEL_BREAKOUT_BONUS": 0.0,
    "CHANNEL_REVERT_DAMP": 0.65,
    "CHANNEL_CONFIRM_IMBALANCE": 0.08,
    "ALIGNED_ENTRY_EDGE_PENALTY": 0.55,
    "ALIGNED_ENTRY_BREAKOUT_PENALTY": 0.20,
    "ALIGNED_TAKE_SIZE_CAP": 4,
    "WORST_ENTRY_EDGE_THRESHOLD": 2.10,
    "WORST_ENTRY_BREAKOUT_THRESHOLD": 1.35,
    "WORST_ENTRY_FLOW_THRESHOLD": 0.14,
    "WORST_ENTRY_DEPTH_THRESHOLD": 0.25,
    "WORST_ENTRY_FIT_THRESHOLD": 0.55,
    "RISK_REDUCE_URGENCY_EXCESS": 24.0,
    "RISK_REDUCE_FLOW_CONFIRM": 0.05,
    "RISK_REDUCE_BREAKOUT_CONFIRM": 0.15,
    "RISK_REDUCE_TAKE_SIZE_CAP": 4,
    "RISK_REDUCE_SLOW_EDGE_THRESHOLD": 2.35,
    "RISK_REDUCE_SLOW_FIT_THRESHOLD": 0.34,
    "RISK_REDUCE_SLOW_DEPTH_THRESHOLD": 0.65,
}


class BaseProductTrader:
    HISTORY_LENGTH = 8

    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        product_memory: Dict[str, dict],
        position_limit: int,
    ) -> None:
        self.product = product
        self.state = state
        self.mid_history = mid_history
        self.product_memory_by_product = product_memory
        raw_memory = product_memory.get(product, {})
        self.product_memory = raw_memory if isinstance(raw_memory, dict) else {}
        self.product_memory_by_product[product] = self.product_memory
        self.position_limit = position_limit
        self.orders: List[Order] = []
        self.diagnostic_events: List[dict] = []
        self.diagnostic_context: Dict[str, object] = {}

        self.order_depth: Optional[OrderDepth] = state.order_depths.get(product)
        self.own_trades = list(state.own_trades.get(product, []))
        self.market_trades = list(state.market_trades.get(product, []))
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
        self.depth_micro: Optional[float] = None
        self.depth_imbalance_short: float = 0.0
        self.depth_imbalance_long: float = 0.0
        self.depth_concentration: float = 0.0
        self.depth_slope: float = 0.0

        self._load_market_state()

    def _depth_profile(
        self,
        levels: List[Tuple[int, int]],
        max_levels: int,
        reference_price: int,
        is_bid: bool,
    ) -> Dict[str, float]:
        selected = levels[: max(1, max_levels)]
        total_volume = sum(float(max(0, volume)) for _price, volume in selected)
        if total_volume <= 0.0:
            return {
                "total_volume": 0.0,
                "vwap": float(reference_price),
                "near_share": 0.0,
                "avg_distance": 0.0,
            }

        weighted_price = sum(float(price) * float(max(0, volume)) for price, volume in selected)
        near_levels = min(2, len(selected))
        near_volume = sum(float(max(0, volume)) for _price, volume in selected[:near_levels])
        weighted_distance = 0.0
        for price, volume in selected:
            distance = (float(reference_price) - float(price)) if is_bid else (float(price) - float(reference_price))
            weighted_distance += max(0.0, distance) * float(max(0, volume))

        return {
            "total_volume": total_volume,
            "vwap": weighted_price / total_volume,
            "near_share": near_volume / total_volume,
            "avg_distance": weighted_distance / total_volume,
        }

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

        short_levels = max(2, int(getattr(self, "DEPTH_LEVELS_SHORT", 3)))
        long_levels = max(short_levels, int(getattr(self, "DEPTH_LEVELS_LONG", 5)))

        bid_short = self._depth_profile(self.buy_levels, short_levels, int(self.best_bid), True)
        ask_short = self._depth_profile(self.sell_levels, short_levels, int(self.best_ask), False)
        bid_long = self._depth_profile(self.buy_levels, long_levels, int(self.best_bid), True)
        ask_long = self._depth_profile(self.sell_levels, long_levels, int(self.best_ask), False)

        short_total = bid_short["total_volume"] + ask_short["total_volume"]
        long_total = bid_long["total_volume"] + ask_long["total_volume"]

        if short_total > 0.0:
            self.depth_micro = (
                bid_short["vwap"] * ask_short["total_volume"]
                + ask_short["vwap"] * bid_short["total_volume"]
            ) / short_total
            self.depth_imbalance_short = (
                bid_short["total_volume"] - ask_short["total_volume"]
            ) / short_total
        else:
            self.depth_micro = self.mid
            self.depth_imbalance_short = 0.0

        if long_total > 0.0:
            self.depth_imbalance_long = (
                bid_long["total_volume"] - ask_long["total_volume"]
            ) / long_total
            self.depth_concentration = bid_long["near_share"] - ask_long["near_share"]
            self.depth_slope = (
                ask_long["avg_distance"] - bid_long["avg_distance"]
            ) / max(1.0, float(self.spread))
        else:
            self.depth_imbalance_long = 0.0
            self.depth_concentration = 0.0
            self.depth_slope = 0.0

        history = self.mid_history.get(self.product, [])
        self.recent_average = sum(history) / len(history) if history else self.mid
        self.momentum = self.mid - self.recent_average

        history.append(self.mid)
        self.mid_history[self.product] = history[-self.HISTORY_LENGTH :]

    def memory_list(self, key: str) -> List[float]:
        values = self.product_memory.get(key)
        if not isinstance(values, list):
            values = []
            self.product_memory[key] = values
        return values

    def append_memory_value(self, key: str, value: float, max_length: int) -> None:
        values = self.memory_list(key)
        values.append(float(value))
        self.product_memory[key] = values[-max_length:]

    def diagnostic_enabled(self) -> bool:
        return self.product == "TOMATOES"

    def diagnostic_value(self, value):
        if isinstance(value, float):
            return round(value, 4)
        if isinstance(value, (int, str, bool)) or value is None:
            return value
        if isinstance(value, dict):
            return {
                str(key): self.diagnostic_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self.diagnostic_value(item) for item in value]
        return str(value)

    def record_diagnostic(self, event_type: str, **payload) -> None:
        if not self.diagnostic_enabled():
            return
        if len(self.diagnostic_events) >= 12:
            return
        event = {
            "et": event_type,
            "p": self.product,
            "ts": int(getattr(self.state, "timestamp", 0)),
        }
        for key, value in payload.items():
            event[str(key)] = self.diagnostic_value(value)
        self.diagnostic_events.append(event)

    def memory_map(self, key: str) -> Dict[str, float]:
        raw = self.product_memory.get(key)
        if not isinstance(raw, dict):
            raw = {}
        cleaned: Dict[str, float] = {}
        for bucket, score in raw.items():
            try:
                cleaned[str(bucket)] = float(score)
            except (TypeError, ValueError):
                continue
        self.product_memory[key] = cleaned
        return cleaned

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
        product_memory: Dict[str, dict],
        position_limit: int,
        params: Optional[Dict[str, float]] = None,
    ) -> None:
        super().__init__(product, state, mid_history, product_memory, position_limit)
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
        product_memory: Dict[str, dict],
        position_limit: int,
        params: Optional[Dict[str, float]] = None,
    ) -> None:
        super().__init__(product, state, mid_history, product_memory, position_limit)
        self.apply_parameter_overrides(self.PARAMETER_DEFAULTS, params)
        self.soft_limit = int(position_limit * self.SOFT_LIMIT_RATIO)

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

    def time_fraction_remaining(self) -> float:
        timestamp = float(getattr(self.state, "timestamp", 0))
        remaining_ticks = max(0.0, self.TIME_HORIZON_TICKS - (timestamp / 100.0))
        return remaining_ticks / self.TIME_HORIZON_TICKS

    def flow_history_length(self) -> int:
        return max(16, int(self.FLOW_LONG_WINDOW) * 2)

    def price_bucket_index(self, price: float) -> int:
        bucket_size = max(1.0, float(self.PRESSURE_PRICE_BUCKET))
        return int(round(price / bucket_size))

    def previous_book_state(self) -> Dict[str, float]:
        previous = self.memory_map("prev_book")
        required = (
            "best_bid",
            "best_ask",
            "best_bid_volume",
            "best_ask_volume",
            "mid",
            "micro",
            "spread",
            "imbalance",
        )
        if not all(key in previous for key in required):
            return {}
        return previous

    def depth_alpha(self) -> float:
        if self.depth_micro is None or self.spread is None or self.mid is None:
            return 0.0

        half_spread = max(1.0, float(self.spread) / 2.0)
        micro_component = float(self.depth_micro) - float(self.mid)
        imbalance_component = (
            0.55 * self.depth_imbalance_short
            + 0.30 * self.depth_imbalance_long
            + 0.15 * self.depth_concentration
        )
        shape_component = imbalance_component + (0.20 * self.depth_slope)
        alpha = micro_component + (half_spread * shape_component)
        return max(-self.ALPHA_CAP, min(self.ALPHA_CAP, alpha))

    def channel_state(self, flow_bias: float, depth_alpha: float) -> Dict[str, float]:
        history = self.memory_list("channel_mid_history")
        window_size = max(8, int(getattr(self, "CHANNEL_WINDOW", 18)))
        window = history[-window_size:]
        half_spread = max(1.0, float(self.spread) / 2.0)

        if len(window) < max(6, window_size // 2):
            return {
                "position": 0.0,
                "direction": 0.0,
                "span": 0.0,
                "high": float(self.mid),
                "low": float(self.mid),
            }

        channel_high = max(window)
        channel_low = min(window)
        span = max(2.0 * half_spread, channel_high - channel_low)
        center = (channel_high + channel_low) / 2.0
        position = (float(self.mid) - center) / max(half_spread, span / 2.0)
        position = max(-1.5, min(1.5, position))

        confirm_imbalance = max(
            float(getattr(self, "CHANNEL_CONFIRM_IMBALANCE", 0.08)),
            float(self.BURST_CONFIRM_IMBALANCE),
        )
        direction = 0.0
        if (
            float(self.mid) >= channel_high - (0.35 * half_spread)
            and float(self.micro) >= float(self.mid)
            and flow_bias >= confirm_imbalance
            and depth_alpha >= -0.10 * half_spread
        ):
            direction = 1.0
        elif (
            float(self.mid) <= channel_low + (0.35 * half_spread)
            and float(self.micro) <= float(self.mid)
            and flow_bias <= -confirm_imbalance
            and depth_alpha <= 0.10 * half_spread * -1.0
        ):
            direction = -1.0

        return {
            "position": position,
            "direction": direction,
            "span": span,
            "high": channel_high,
            "low": channel_low,
        }

    def market_flow_metrics(self) -> Dict[str, float]:
        previous = self.previous_book_state()
        if not previous:
            return {
                "activity": 0.0,
                "signed_flow": 0.0,
                "bias": 0.0,
                "price_pressure": 0.0,
                "flow_acceleration": 0.0,
                "compression": 0.0,
                "persistence": 0.0,
                "micro_drift": 0.0,
                "mid_drift": 0.0,
                "imbalance_drift": 0.0,
                "prev_available": 0.0,
            }

        scale = max(
            1.0,
            float(self.spread) / 2.0,
            float(previous["spread"]) / 2.0,
        )
        top_volume_scale = max(
            1.0,
            float(previous["best_bid_volume"]) + float(previous["best_ask_volume"]),
        )

        bid_up = max(0.0, float(self.best_bid) - float(previous["best_bid"])) / scale
        bid_down = max(0.0, float(previous["best_bid"]) - float(self.best_bid)) / scale
        ask_up = max(0.0, float(self.best_ask) - float(previous["best_ask"])) / scale
        ask_down = max(0.0, float(previous["best_ask"]) - float(self.best_ask)) / scale

        if float(self.best_bid) == float(previous["best_bid"]):
            bid_depletion = max(0.0, float(previous["best_bid_volume"]) - float(self.best_bid_volume)) / top_volume_scale
            bid_rebuild = max(0.0, float(self.best_bid_volume) - float(previous["best_bid_volume"])) / top_volume_scale
        elif float(self.best_bid) > float(previous["best_bid"]):
            bid_depletion = 0.0
            bid_rebuild = float(self.best_bid_volume) / top_volume_scale
        else:
            bid_depletion = float(previous["best_bid_volume"]) / top_volume_scale
            bid_rebuild = 0.0

        if float(self.best_ask) == float(previous["best_ask"]):
            ask_depletion = max(0.0, float(previous["best_ask_volume"]) - float(self.best_ask_volume)) / top_volume_scale
            ask_rebuild = max(0.0, float(self.best_ask_volume) - float(previous["best_ask_volume"])) / top_volume_scale
        elif float(self.best_ask) > float(previous["best_ask"]):
            ask_depletion = float(previous["best_ask_volume"]) / top_volume_scale
            ask_rebuild = 0.0
        else:
            ask_depletion = 0.0
            ask_rebuild = float(self.best_ask_volume) / top_volume_scale

        micro_drift = (float(self.micro) - float(previous["micro"])) / scale
        mid_drift = (float(self.mid) - float(previous["mid"])) / scale
        imbalance_drift = float(self.imbalance) - float(previous["imbalance"])
        compression = max(
            0.0,
            (float(previous["spread"]) - float(self.spread)) / max(1.0, float(previous["spread"])),
        )

        buy_impulse = (
            self.BOOK_STEP_WEIGHT * (bid_up + ask_up)
            + self.BOOK_DEPLETION_WEIGHT * ask_depletion
            + self.BOOK_REBUILD_WEIGHT * bid_rebuild
            + self.MICRO_DRIFT_WEIGHT * max(0.0, micro_drift)
            + self.MID_DRIFT_WEIGHT * max(0.0, mid_drift)
            + 0.35 * max(0.0, imbalance_drift)
        )
        sell_impulse = (
            self.BOOK_STEP_WEIGHT * (bid_down + ask_down)
            + self.BOOK_DEPLETION_WEIGHT * bid_depletion
            + self.BOOK_REBUILD_WEIGHT * ask_rebuild
            + self.MICRO_DRIFT_WEIGHT * max(0.0, -micro_drift)
            + self.MID_DRIFT_WEIGHT * max(0.0, -mid_drift)
            + 0.35 * max(0.0, -imbalance_drift)
        )

        activity = (
            buy_impulse
            + sell_impulse
            + abs(micro_drift)
            + abs(mid_drift)
            + abs(imbalance_drift)
            + compression
        )
        signed_flow = buy_impulse - sell_impulse
        flow_bias = 0.0 if activity <= 1e-9 else signed_flow / max(1.0, activity)
        price_pressure = (
            0.60 * micro_drift
            + 0.40 * mid_drift
            + 0.20 * imbalance_drift
        )

        signed_history = self.memory_list("signed_flow_history")
        short_window = signed_history[-int(self.FLOW_SHORT_WINDOW) :]
        long_window = signed_history[-int(self.FLOW_LONG_WINDOW) :]
        short_average = (sum(short_window) / len(short_window)) if short_window else 0.0
        long_average = (sum(long_window) / len(long_window)) if long_window else 0.0
        acceleration_scale = max(1.0, abs(short_average), abs(long_average))
        flow_acceleration = (short_average - long_average) / acceleration_scale

        imbalance_history = self.memory_list("imbalance_history")
        micro_premium_history = self.memory_list("micro_premium_history")
        short_imbalance = imbalance_history[-int(self.FLOW_SHORT_WINDOW) :]
        long_imbalance = imbalance_history[-int(self.FLOW_LONG_WINDOW) :]
        short_micro = micro_premium_history[-int(self.FLOW_SHORT_WINDOW) :]
        long_micro = micro_premium_history[-int(self.FLOW_LONG_WINDOW) :]
        imbalance_persistence = (
            (sum(short_imbalance) / len(short_imbalance)) - (sum(long_imbalance) / len(long_imbalance))
            if short_imbalance and long_imbalance
            else 0.0
        )
        micro_persistence = (
            (sum(short_micro) / len(short_micro)) - (sum(long_micro) / len(long_micro))
            if short_micro and long_micro
            else 0.0
        )
        persistence = (
            self.PERSISTENCE_WEIGHT * imbalance_persistence
            + (1.0 - self.PERSISTENCE_WEIGHT) * micro_persistence
        )

        return {
            "activity": activity,
            "signed_flow": signed_flow,
            "bias": flow_bias,
            "price_pressure": price_pressure,
            "flow_acceleration": flow_acceleration,
            "compression": compression,
            "persistence": persistence,
            "micro_drift": micro_drift,
            "mid_drift": mid_drift,
            "imbalance_drift": imbalance_drift,
            "prev_available": 1.0,
        }

    def percentile_threshold(self, values: List[float], percentile: float) -> float:
        if not values:
            return 0.0

        ordered = sorted(float(value) for value in values)
        clipped = max(0.0, min(0.99, percentile))
        index = min(len(ordered) - 1, max(0, int(math.floor(clipped * (len(ordered) - 1)))))
        return ordered[index]

    def burst_score(self, flow_metrics: Dict[str, float]) -> float:
        activity = flow_metrics["activity"]
        flow_bias = flow_metrics["bias"]
        if activity <= self.BOOK_ACTIVITY_FLOOR or abs(flow_bias) < 0.08:
            return 0.0

        activity_history = self.memory_list("activity_history")
        signals: List[float] = []
        for window_size in (int(self.FLOW_SHORT_WINDOW), int(self.FLOW_LONG_WINDOW)):
            window = activity_history[-window_size:]
            if len(window) < max(6, window_size - 2):
                continue

            threshold = self.percentile_threshold(window, self.BURST_PERCENTILE)
            baseline = sum(window) / len(window)
            reference = max(self.BOOK_ACTIVITY_FLOOR, threshold, baseline * 1.08)
            if activity >= reference:
                signals.append((activity - reference) / reference)

        if not signals:
            return 0.0

        burst = min(2.0, (sum(signals) / len(signals)) * 2.0 + (0.25 * abs(flow_bias)))
        if flow_bias * self.imbalance < self.BURST_CONFIRM_IMBALANCE:
            burst *= 0.65
        if flow_bias * flow_metrics["price_pressure"] < 0:
            burst *= 0.75
        if flow_bias * flow_metrics["persistence"] < 0:
            burst *= 0.80
        if flow_metrics["compression"] > 0:
            burst += self.SPREAD_COMPRESSION_WEIGHT * 0.25 * min(1.0, flow_metrics["compression"])
        if flow_metrics["flow_acceleration"] * flow_bias > 0:
            burst += 0.15 * min(1.0, abs(flow_metrics["flow_acceleration"]))

        return math.copysign(min(2.0, burst), flow_bias)

    def update_pressure_memory(self, flow_metrics: Dict[str, float]) -> float:
        pressure = self.memory_map("pressure_buckets")
        decayed: Dict[str, float] = {}

        for bucket, score in pressure.items():
            decayed_score = float(score) * self.PRESSURE_MEMORY_DECAY
            if abs(decayed_score) >= 0.05:
                decayed[bucket] = decayed_score

        activity = flow_metrics["activity"]
        if activity > 0.0:
            impulse = flow_metrics["bias"] * min(2.0, activity)
            previous = self.previous_book_state()

            if abs(impulse) >= 0.10:
                if impulse > 0:
                    updates = [
                        (float(self.best_bid), 1.0 + (0.5 * max(0.0, flow_metrics["compression"]))),
                        (float(self.mid), 0.20),
                    ]
                    if previous and float(self.best_ask) > float(previous["best_ask"]):
                        updates.append((float(previous["best_ask"]), 0.45))
                    elif flow_metrics["price_pressure"] > 0:
                        updates.append((float(self.best_ask), 0.20))
                else:
                    updates = [
                        (float(self.best_ask), 1.0 + (0.5 * max(0.0, flow_metrics["compression"]))),
                        (float(self.mid), 0.20),
                    ]
                    if previous and float(self.best_bid) < float(previous["best_bid"]):
                        updates.append((float(previous["best_bid"]), 0.45))
                    elif flow_metrics["price_pressure"] < 0:
                        updates.append((float(self.best_bid), 0.20))

                for price, weight in updates:
                    bucket = str(self.price_bucket_index(price))
                    decayed[bucket] = decayed.get(bucket, 0.0) + (impulse * weight)

        if len(decayed) > 24:
            strongest = sorted(decayed.items(), key=lambda item: abs(item[1]), reverse=True)[:24]
            decayed = {bucket: score for bucket, score in strongest}

        self.product_memory["pressure_buckets"] = decayed
        return self.pressure_bias()

    def pressure_bias(self) -> float:
        pressure = self.memory_map("pressure_buckets")
        bucket_size = max(1.0, float(self.PRESSURE_PRICE_BUCKET))
        support = 0.0
        resistance = 0.0
        breakout_tail = 0.0

        for bucket, raw_score in pressure.items():
            try:
                bucket_price = int(bucket) * bucket_size
            except ValueError:
                continue

            distance = abs(bucket_price - float(self.mid)) / bucket_size
            if distance > 6.0:
                continue

            weight = 1.0 / (1.0 + distance)
            score = float(raw_score)
            if bucket_price <= float(self.mid) and score > 0:
                support += score * weight
            elif bucket_price >= float(self.mid) and score < 0:
                resistance += abs(score) * weight
            else:
                breakout_tail += 0.35 * score * weight

        bias = (support - resistance) + breakout_tail
        return max(-2.5, min(2.5, bias / 6.0))

    def breakout_score(
        self,
        flow_metrics: Dict[str, float],
        burst_score: float,
        pressure_bias: float,
        predicted_edge: float,
        fit_quality: float,
        depth_alpha: float,
        channel_state: Dict[str, float],
    ) -> float:
        if burst_score == 0.0:
            return 0.0
        if abs(flow_metrics["bias"]) < max(0.12, self.BURST_CONFIRM_IMBALANCE):
            return 0.0
        if flow_metrics["activity"] < self.BOOK_ACTIVITY_FLOOR and abs(flow_metrics["price_pressure"]) < 0.20:
            return 0.0

        direction = math.copysign(1.0, burst_score)
        conviction = abs(burst_score)

        if flow_metrics["bias"] * direction > 0:
            conviction += 0.35 * abs(flow_metrics["bias"])
        if self.imbalance * direction >= self.BURST_CONFIRM_IMBALANCE:
            conviction += 0.25
        if flow_metrics["price_pressure"] * direction > 0:
            conviction += 0.20 * min(1.0, abs(flow_metrics["price_pressure"]))
        if flow_metrics["persistence"] * direction > 0:
            conviction += 0.20 * min(1.0, abs(flow_metrics["persistence"]))
        if flow_metrics["compression"] > 0 and flow_metrics["price_pressure"] * direction > 0:
            conviction += 0.20 * min(1.0, flow_metrics["compression"])
        if flow_metrics["flow_acceleration"] * direction > 0:
            conviction += 0.20 * min(1.0, abs(flow_metrics["flow_acceleration"]))
        if pressure_bias * direction > 0:
            conviction += 0.25 * abs(pressure_bias)
        else:
            conviction *= 0.75
        if (float(self.micro) - float(self.mid)) * direction > 0:
            conviction += 0.15
        if predicted_edge * direction > 0:
            conviction += 0.10 * max(0.5, fit_quality)
        if self.momentum * direction > -0.25:
            conviction += 0.10

        return direction * min(2.5, conviction)

    def store_flow_metrics(self, flow_metrics: Dict[str, float]) -> None:
        history_length = self.flow_history_length()
        half_spread = max(1.0, float(self.spread) / 2.0)
        self.append_memory_value("activity_history", flow_metrics["activity"], history_length)
        self.append_memory_value("signed_flow_history", flow_metrics["signed_flow"], history_length)
        self.append_memory_value("bias_history", flow_metrics["bias"], history_length)
        self.append_memory_value("price_pressure_history", flow_metrics["price_pressure"], history_length)
        self.append_memory_value("compression_history", flow_metrics["compression"], history_length)
        self.append_memory_value("imbalance_history", self.imbalance, history_length)
        self.append_memory_value("micro_premium_history", (float(self.micro) - float(self.mid)) / half_spread, history_length)
        channel_history = max(history_length, int(getattr(self, "CHANNEL_WINDOW", 18)) + 4)
        self.append_memory_value("channel_mid_history", float(self.mid), channel_history)
        self.product_memory["prev_book"] = {
            "best_bid": float(self.best_bid),
            "best_ask": float(self.best_ask),
            "best_bid_volume": float(self.best_bid_volume),
            "best_ask_volume": float(self.best_ask_volume),
            "mid": float(self.mid),
            "micro": float(self.micro),
            "spread": float(self.spread),
            "imbalance": float(self.imbalance),
        }

    def hybrid_alpha(self) -> Tuple[float, float]:
        reference_price = float(self.recent_average)
        half_spread = max(1.0, float(self.spread) / 2.0)
        bias_history = self.memory_list("bias_history")
        short_bias = bias_history[-int(self.FLOW_SHORT_WINDOW) :]
        smoothed_bias = (sum(short_bias) / len(short_bias)) if short_bias else self.imbalance
        flow_signal = smoothed_bias * half_spread * self.ALPHA_FLOW_SPREAD_SCALE
        hybrid_fair = (
            self.ALPHA_REFERENCE_WEIGHT * reference_price
            + self.ALPHA_MID_WEIGHT * float(self.mid)
            + self.ALPHA_MICRO_WEIGHT * float(self.micro)
            + self.ALPHA_FLOW_WEIGHT * (float(self.mid) + flow_signal)
        )
        alpha = hybrid_fair - float(self.mid)
        alpha = max(-self.ALPHA_CAP, min(self.ALPHA_CAP, alpha))
        return hybrid_fair, alpha

    def guarded_hybrid_alpha(
        self,
        hybrid_alpha: float,
        regression_edge: float,
        regime: str,
        channel_position: float = 0.0,
        channel_direction: float = 0.0,
    ) -> float:
        weight = 1.0
        if regime == "range":
            weight *= self.RANGE_ALPHA_DAMP

        if hybrid_alpha * regression_edge < 0:
            weight *= self.CONFLICT_ALPHA_DAMP

        if hybrid_alpha * self.imbalance < 0:
            weight *= self.CONFLICT_ALPHA_DAMP

        if hybrid_alpha * self.momentum < 0:
            weight *= self.MOMENTUM_ALPHA_DAMP

        if (
            regime == "range"
            and channel_direction == 0.0
            and abs(channel_position) >= 0.85
            and hybrid_alpha * channel_position > 0
        ):
            weight *= self.CHANNEL_REVERT_DAMP

        position = self.projected_position()
        if hybrid_alpha * position > 0:
            abs_pos = abs(position)
            if abs_pos >= self.POSITION_ALPHA_DAMP_START:
                if abs_pos >= self.POSITION_ALPHA_DAMP_END:
                    weight *= 0.0
                else:
                    span = self.POSITION_ALPHA_DAMP_END - self.POSITION_ALPHA_DAMP_START
                    ratio = (abs_pos - self.POSITION_ALPHA_DAMP_START) / max(1e-9, span)
                    weight *= max(0.0, 1.0 - ratio)

        return hybrid_alpha * weight

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
        breakout_score: float = 0.0,
        flow_bias: float = 0.0,
        channel_direction: float = 0.0,
        depth_alpha: float = 0.0,
    ) -> str:
        trend_threshold = self.TREND_EDGE_THRESHOLD * self.ALPHA_THRESHOLD_SCALE
        momentum_threshold = float(getattr(self, "MOMENTUM_TREND_THRESHOLD", 0.75))
        if (
            float(self.spread) >= self.TOXIC_SPREAD_THRESHOLD
            and volatility >= self.TOXIC_VOLATILITY_THRESHOLD
            and abs(breakout_score) < 0.8
        ):
            return "volatile"
        if (
            breakout_score >= 1.0
            and flow_bias >= self.BURST_CONFIRM_IMBALANCE
            and self.momentum >= -momentum_threshold
            and float(self.micro) >= float(self.mid)
        ):
            return "trend_up"
        if (
            breakout_score <= -1.0
            and flow_bias <= -self.BURST_CONFIRM_IMBALANCE
            and self.momentum <= momentum_threshold
            and float(self.micro) <= float(self.mid)
        ):
            return "trend_down"
        if (
            predicted_edge >= trend_threshold - (0.20 * max(0.0, breakout_score))
            and fit_quality >= max(0.25, self.FIT_THRESHOLD - (0.08 * max(0.0, breakout_score)))
            and self.imbalance >= self.TREND_IMBALANCE_THRESHOLD
            and self.momentum >= momentum_threshold
            and float(self.micro) >= float(self.mid)
        ):
            return "trend_up"
        if (
            predicted_edge <= -trend_threshold - (0.20 * min(0.0, breakout_score))
            and fit_quality >= max(0.25, self.FIT_THRESHOLD + (0.08 * min(0.0, breakout_score)))
            and self.imbalance <= -self.TREND_IMBALANCE_THRESHOLD
            and self.momentum <= -momentum_threshold
            and float(self.micro) <= float(self.mid)
        ):
            return "trend_down"
        return "range"

    def target_band(
        self,
        regime: str,
        predicted_edge: float,
        fit_quality: float,
        breakout_score: float = 0.0,
    ) -> Tuple[int, int]:
        conviction = abs(predicted_edge) * max(0.5, fit_quality) + (0.55 * abs(breakout_score))
        if regime == "trend_up":
            if breakout_score >= 1.4:
                return (26, 48) if conviction >= self.STRONG_TREND_EDGE else (14, 32)
            return (22, 44) if conviction >= self.STRONG_TREND_EDGE else (10, 28)
        if regime == "trend_down":
            if breakout_score <= -1.4:
                return (-48, -26) if conviction >= self.STRONG_TREND_EDGE else (-32, -14)
            return (-44, -22) if conviction >= self.STRONG_TREND_EDGE else (-28, -10)
        if regime == "volatile":
            return -6, 6
        return -14, 14

    def target_position(
        self,
        regime: str,
        predicted_edge: float,
        fit_quality: float,
        breakout_score: float = 0.0,
    ) -> int:
        lower, upper = self.target_band(regime, predicted_edge, fit_quality, breakout_score)
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

    def side_sign(self, side: str) -> int:
        return 1 if side == "BUY" else -1

    def is_risk_reducing_trade(self, side: str) -> bool:
        return self.projected_position() * self.side_sign(side) < 0

    def is_aligned_entry_trade(self, side: str, target_position: int) -> bool:
        side_sign = self.side_sign(side)
        position = self.projected_position()
        return side_sign * position >= 0 and side_sign * target_position > side_sign * position

    def quantity_toward_target(self, side: str, position_before: int, target_position: int) -> int:
        if side == "BUY":
            return max(0, target_position - position_before)
        return max(0, position_before - target_position)

    def allow_risk_reducing_take(
        self,
        side: str,
        regime: str,
        position_before: int,
        target_position: int,
        predicted_edge: float,
        fit_quality: float,
        depth_alpha: float,
        breakout_score: float,
        flow_bias: float,
    ) -> bool:
        if regime != "range":
            return True

        excess_inventory = abs(position_before - target_position)
        if excess_inventory >= self.RISK_REDUCE_URGENCY_EXCESS or abs(position_before) >= self.soft_limit:
            return True

        side_sign = self.side_sign(side)
        flow_confirm = flow_bias * side_sign >= self.RISK_REDUCE_FLOW_CONFIRM
        breakout_confirm = breakout_score * side_sign >= self.RISK_REDUCE_BREAKOUT_CONFIRM
        if flow_confirm or breakout_confirm:
            return True

        half_spread = max(1.0, float(self.spread) / 2.0)
        depth_signal = (depth_alpha / half_spread) * side_sign
        return (
            predicted_edge * side_sign >= self.RISK_REDUCE_SLOW_EDGE_THRESHOLD
            and fit_quality >= self.RISK_REDUCE_SLOW_FIT_THRESHOLD
            and depth_signal >= self.RISK_REDUCE_SLOW_DEPTH_THRESHOLD
        )

    def allow_worst_side_take(
        self,
        side: str,
        regime: str,
        target_position: int,
        predicted_edge: float,
        fit_quality: float,
        breakout_score: float,
        depth_alpha: float,
        flow_bias: float,
    ) -> bool:
        if self.is_risk_reducing_trade(side):
            return True
        if not self.is_aligned_entry_trade(side, target_position):
            return False

        side_sign = self.side_sign(side)
        half_spread = max(1.0, float(self.spread) / 2.0)
        depth_signal = (depth_alpha / half_spread) * side_sign
        regime_aligned = (side == "BUY" and regime == "trend_up") or (
            side == "SELL" and regime == "trend_down"
        )
        return (
            regime_aligned
            and fit_quality >= self.WORST_ENTRY_FIT_THRESHOLD
            and predicted_edge * side_sign >= self.WORST_ENTRY_EDGE_THRESHOLD
            and breakout_score * side_sign >= self.WORST_ENTRY_BREAKOUT_THRESHOLD
            and flow_bias * side_sign >= self.WORST_ENTRY_FLOW_THRESHOLD
            and depth_signal >= self.WORST_ENTRY_DEPTH_THRESHOLD
        )

    def log_take_decision(
        self,
        side: str,
        price: int,
        threshold: float,
        target_position: int,
        position_before: int,
        position_after: int,
        candidate_quantity: int,
        executed_quantity: int,
        gate: str,
        gate_allowed: bool,
        aligned_entry: bool,
        risk_reducing: bool,
    ) -> None:
        side_sign = self.side_sign(side)
        crosses_flat = (
            risk_reducing
            and executed_quantity > 0
            and abs(position_after) > abs(position_before)
            and position_before * position_after <= 0
        )
        ctx = self.diagnostic_context
        self.record_diagnostic(
            "take",
            s=side,
            px=int(price),
            thr=threshold,
            gap=(threshold - float(price)) * side_sign,
            edge_mid=(float(self.mid) - float(price)) * side_sign,
            edge_fair=(float(ctx.get("adjusted_fair", self.mid)) - float(price)) * side_sign,
            pb=position_before,
            pa=position_after,
            tp=target_position,
            cq=int(candidate_quantity),
            xq=int(executed_quantity),
            rr=risk_reducing,
            ae=aligned_entry,
            xf=crosses_flat,
            gate=gate,
            ok=gate_allowed,
            regime=ctx.get("regime"),
            pred=ctx.get("predicted_edge"),
            reg=ctx.get("regression_edge"),
            fit=ctx.get("fit_quality"),
            vol=ctx.get("volatility"),
            breakout=ctx.get("breakout_score"),
            flow=ctx.get("flow_bias"),
            depth=ctx.get("depth_alpha"),
            pressure=ctx.get("pressure_bias"),
            hybrid=ctx.get("hybrid_alpha"),
            cpos=ctx.get("channel_position"),
            cdir=ctx.get("channel_direction"),
            spread=self.spread,
            mt=len(self.market_trades),
            ot=len(self.own_trades),
        )

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
        hybrid_alpha: float,
        pressure_bias: float,
        depth_alpha: float,
        channel_position: float,
        channel_direction: float,
    ) -> float:
        line_gap = predicted_now - float(self.mid)
        scaled_imbalance = self.imbalance * self.ALPHA_IMBALANCE_SCALE
        half_spread = max(1.0, float(self.spread) / 2.0)
        fair = (
            self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
            + self.HISTORY_WEIGHT * float(self.recent_average)
            + self.REGRESSION_WEIGHT * predicted_next
            + self.IMBALANCE_WEIGHT * scaled_imbalance
        )
        fair += self.FAIR_ALPHA_WEIGHT * hybrid_alpha
        fair += self.DEPTH_ALPHA_WEIGHT * depth_alpha
        fair += self.PRESSURE_BIAS_SCALE * pressure_bias * (0.65 if regime == "range" else 1.0)
        fair += (target_position - self.projected_position()) / self.POSITION_BIAS_DIVISOR
        channel_adjustment = self.CHANNEL_POSITION_WEIGHT * channel_position * half_spread
        fair -= self.CHANNEL_REVERT_DAMP * channel_adjustment
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
        hybrid_alpha: float,
        pressure_bias: float,
        depth_alpha: float,
        channel_position: float,
        channel_direction: float,
    ) -> float:
        fair = self.fair_value(
            regime,
            target_position,
            predicted_now,
            predicted_next,
            hybrid_alpha,
            pressure_bias,
            depth_alpha,
            channel_position,
            channel_direction,
        )
        return fair - (self.projected_position() * self.INVENTORY_SKEW)

    def take_edge(
        self,
        side: str,
        target_position: int,
        regime: str,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
        breakout_score: float = 0.0,
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

        if self.is_aligned_entry_trade(side, target_position):
            normalized_position = abs(position) / max(1.0, float(self.position_limit))
            edge += self.ALIGNED_ENTRY_EDGE_PENALTY * (1.0 + normalized_position)
            if breakout_score * self.side_sign(side) <= 0:
                edge += self.ALIGNED_ENTRY_BREAKOUT_PENALTY
            if predicted_edge * self.side_sign(side) <= self.TREND_EDGE_THRESHOLD:
                edge += 0.20

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

        if breakout_score != 0.0:
            breakout_direction = math.copysign(1.0, breakout_score)
            breakout_conviction = min(2.0, abs(breakout_score))
            aligned = (side == "BUY" and breakout_direction > 0) or (
                side == "SELL" and breakout_direction < 0
            )
            if aligned:
                edge -= 0.10 * breakout_conviction
            else:
                edge += 0.12 * breakout_conviction

        return max(0.5, edge)

    def quote_edge(
        self,
        regime: str,
        volatility: float,
        fit_quality: float,
        breakout_score: float = 0.0,
    ) -> float:
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
        if abs(breakout_score) >= 1.10 and regime in {"trend_up", "trend_down"}:
            edge -= min(0.90, self.BREAKOUT_QUOTE_TIGHTEN * 0.35 * abs(breakout_score))
        return min(self.MAX_QUOTE_EDGE, max(1.0, edge))

    def passive_quotes(
        self,
        adjusted_fair: float,
        regime: str,
        target_position: int,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
        breakout_score: float = 0.0,
    ) -> Tuple[Optional[int], Optional[int]]:
        quote_edge = self.quote_edge(regime, volatility, fit_quality, breakout_score)
        buy_quote = math.floor(adjusted_fair - quote_edge)
        sell_quote = math.ceil(adjusted_fair + quote_edge)
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

        breakout_shift = int(round(min(1.0, abs(breakout_score) * self.BREAKOUT_QUOTE_TIGHTEN)))
        if breakout_score > 0:
            if buy_quote is not None and position < target_position:
                buy_quote = min(int(self.best_ask) - 1, buy_quote + breakout_shift)
            if sell_quote is not None and position > 0:
                sell_quote += breakout_shift
        elif breakout_score < 0:
            if sell_quote is not None and position > target_position:
                sell_quote = max(int(self.best_bid) + 1, sell_quote - breakout_shift)
            if buy_quote is not None and position < 0:
                buy_quote -= breakout_shift

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

    def take_orders(
        self,
        regime: str,
        target_position: int,
        adjusted_fair: float,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
        depth_alpha: float,
        flow_bias: float,
        breakout_score: float = 0.0,
    ) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        buy_threshold = adjusted_fair - self.take_edge(
            "BUY",
            target_position,
            regime,
            predicted_edge,
            fit_quality,
            volatility,
            breakout_score,
        )
        if regime == "trend_down" and predicted_edge <= -self.TREND_EDGE_THRESHOLD:
            buy_threshold -= self.TREND_HOLD_EXIT_BONUS + self.TREND_SELL_HOLD_EXTRA
        if regime == "trend_down" and predicted_edge <= -self.STRONG_TREND_EDGE:
            buy_threshold -= self.STRONG_TREND_HOLD_EXIT_BONUS + self.TREND_SELL_HOLD_EXTRA
        if breakout_score <= -0.75:
            buy_threshold -= self.BREAKOUT_HOLD_BONUS * min(2.0, abs(breakout_score))
        buy_threshold -= self.HOLD_TIME_COEF * self.time_fraction_remaining()
        buy_threshold -= self.HOLD_VOL_COEF * min(3.0, volatility)

        if (
            int(self.best_ask) <= buy_threshold
            and self.buy_capacity > 0
        ):
            take_limit = self.MAX_TAKE_SIZE + (int(self.TREND_ENTRY_TAKE_BONUS) if regime == "trend_up" else 0)
            position_before = self.projected_position()
            aligned_entry = self.is_aligned_entry_trade("BUY", target_position)
            risk_reducing = self.is_risk_reducing_trade("BUY")
            target_limit = self.quantity_toward_target("BUY", position_before, target_position)
            gate = "free"
            gate_allowed = True

            if risk_reducing:
                gate_allowed = self.allow_risk_reducing_take(
                    "BUY",
                    regime,
                    position_before,
                    target_position,
                    predicted_edge,
                    fit_quality,
                    depth_alpha,
                    breakout_score,
                    flow_bias,
                )
                gate = "risk_reduce_allow" if gate_allowed else "risk_reduce_block"
            elif regime != "range" and position_before >= target_position:
                gate = "target_block"
                gate_allowed = False
            elif aligned_entry:
                gate_allowed = self.allow_worst_side_take(
                    "BUY",
                    regime,
                    target_position,
                    predicted_edge,
                    fit_quality,
                    breakout_score,
                    depth_alpha,
                    flow_bias,
                )
                gate = "aligned_allow" if gate_allowed else "aligned_block"
            elif risk_reducing:
                gate = "risk_reduce_free"
            else:
                gate = "non_aligned_free"

            quantity = 0
            executed_quantity = 0
            if gate_allowed:
                quantity = min(self.best_ask_volume, take_limit)
                if risk_reducing and regime == "range":
                    quantity = min(quantity, int(self.RISK_REDUCE_TAKE_SIZE_CAP))
                if aligned_entry:
                    quantity = min(quantity, int(self.ALIGNED_TAKE_SIZE_CAP))
                if regime == "range" or risk_reducing or aligned_entry:
                    quantity = min(quantity, target_limit)
                elif regime != "range":
                    quantity = min(quantity, max(1, target_position - position_before))
                before = self.buy_capacity
                self.add_buy(int(self.best_ask), quantity)
                executed_quantity = before - self.buy_capacity
                took_buy = executed_quantity > 0

            self.log_take_decision(
                "BUY",
                int(self.best_ask),
                buy_threshold,
                target_position,
                position_before,
                self.projected_position(),
                quantity,
                executed_quantity,
                gate,
                gate_allowed,
                aligned_entry,
                risk_reducing,
            )

        sell_threshold = adjusted_fair + self.take_edge(
            "SELL",
            target_position,
            regime,
            predicted_edge,
            fit_quality,
            volatility,
            breakout_score,
        )
        if regime == "trend_up" and predicted_edge >= self.TREND_EDGE_THRESHOLD:
            sell_threshold += self.TREND_HOLD_EXIT_BONUS + self.TREND_SELL_HOLD_EXTRA
        if regime == "trend_up" and predicted_edge >= self.STRONG_TREND_EDGE:
            sell_threshold += self.STRONG_TREND_HOLD_EXIT_BONUS + self.TREND_SELL_HOLD_EXTRA
        if breakout_score >= 0.75:
            sell_threshold += self.BREAKOUT_HOLD_BONUS * min(2.0, abs(breakout_score))
        sell_threshold += self.HOLD_TIME_COEF * self.time_fraction_remaining()
        sell_threshold += self.HOLD_VOL_COEF * min(3.0, volatility)

        if (
            int(self.best_bid) >= sell_threshold
            and self.sell_capacity > 0
        ):
            take_limit = self.MAX_TAKE_SIZE + (int(self.TREND_ENTRY_TAKE_BONUS) if regime == "trend_down" else 0)
            position_before = self.projected_position()
            aligned_entry = self.is_aligned_entry_trade("SELL", target_position)
            risk_reducing = self.is_risk_reducing_trade("SELL")
            target_limit = self.quantity_toward_target("SELL", position_before, target_position)
            gate = "free"
            gate_allowed = True

            if risk_reducing:
                gate_allowed = self.allow_risk_reducing_take(
                    "SELL",
                    regime,
                    position_before,
                    target_position,
                    predicted_edge,
                    fit_quality,
                    depth_alpha,
                    breakout_score,
                    flow_bias,
                )
                gate = "risk_reduce_allow" if gate_allowed else "risk_reduce_block"
            elif regime != "range" and position_before <= target_position:
                gate = "target_block"
                gate_allowed = False
            elif aligned_entry:
                gate_allowed = self.allow_worst_side_take(
                    "SELL",
                    regime,
                    target_position,
                    predicted_edge,
                    fit_quality,
                    breakout_score,
                    depth_alpha,
                    flow_bias,
                )
                gate = "aligned_allow" if gate_allowed else "aligned_block"
            elif risk_reducing:
                gate = "risk_reduce_free"
            else:
                gate = "non_aligned_free"

            quantity = 0
            executed_quantity = 0
            if gate_allowed:
                quantity = min(self.best_bid_volume, take_limit)
                if risk_reducing and regime == "range":
                    quantity = min(quantity, int(self.RISK_REDUCE_TAKE_SIZE_CAP))
                if aligned_entry:
                    quantity = min(quantity, int(self.ALIGNED_TAKE_SIZE_CAP))
                if regime == "range" or risk_reducing or aligned_entry:
                    quantity = min(quantity, target_limit)
                elif regime != "range":
                    quantity = min(quantity, max(1, position_before - target_position))
                before = self.sell_capacity
                self.add_sell(int(self.best_bid), quantity)
                executed_quantity = before - self.sell_capacity
                took_sell = executed_quantity > 0

            self.log_take_decision(
                "SELL",
                int(self.best_bid),
                sell_threshold,
                target_position,
                position_before,
                self.projected_position(),
                quantity,
                executed_quantity,
                gate,
                gate_allowed,
                aligned_entry,
                risk_reducing,
            )

        return took_buy, took_sell

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        predicted_now, predicted_next, fit_quality, volatility = self.regression_metrics()
        regression_edge = (predicted_next - float(self.mid)) * self.ALPHA_EDGE_SCALE
        flow_metrics = self.market_flow_metrics()
        depth_alpha = self.depth_alpha()
        channel_state = self.channel_state(flow_metrics["bias"], depth_alpha)
        burst_score = self.burst_score(flow_metrics)
        pressure_bias = self.update_pressure_memory(flow_metrics)
        breakout_score = self.breakout_score(
            flow_metrics,
            burst_score,
            pressure_bias,
            regression_edge,
            fit_quality,
            depth_alpha,
            channel_state,
        )
        if breakout_score * regression_edge < 0:
            breakout_score *= 0.35
        if breakout_score * self.momentum < 0:
            breakout_score *= 0.50
        if pressure_bias * regression_edge < 0:
            pressure_bias *= 0.60
        _hybrid_fair, hybrid_alpha = self.hybrid_alpha()
        provisional_edge = (
            regression_edge
            + (self.BREAKOUT_FOLLOW_SCALE * breakout_score)
            + (0.20 * pressure_bias)
        )
        provisional_regime = self.classify_state(
            provisional_edge,
            fit_quality,
            volatility,
            breakout_score,
            flow_metrics["bias"],
            float(channel_state["direction"]),
            depth_alpha,
        )
        hybrid_alpha = self.guarded_hybrid_alpha(
            hybrid_alpha,
            regression_edge,
            provisional_regime,
            float(channel_state["position"]),
            float(channel_state["direction"]),
        )
        predicted_edge = (
            (1.0 - self.ALPHA_BLEND_WEIGHT) * regression_edge
            + self.ALPHA_BLEND_WEIGHT * hybrid_alpha
            + self.BREAKOUT_FOLLOW_SCALE * breakout_score
            + (0.20 * pressure_bias)
        )
        predicted_next = float(self.mid) + predicted_edge
        regime = self.classify_state(
            predicted_edge,
            fit_quality,
            volatility,
            breakout_score,
            flow_metrics["bias"],
            float(channel_state["direction"]),
            depth_alpha,
        )
        target_position = self.target_position(regime, predicted_edge, fit_quality, breakout_score)
        adjusted_fair = self.adjusted_fair_value(
            regime,
            target_position,
            predicted_now,
            predicted_next,
            hybrid_alpha,
            pressure_bias,
            depth_alpha,
            float(channel_state["position"]),
            float(channel_state["direction"]),
        ) - self.reservation_adjustment(regime, target_position, predicted_edge, volatility)
        self.diagnostic_context = {
            "regime": regime,
            "target_position": target_position,
            "adjusted_fair": adjusted_fair,
            "predicted_edge": predicted_edge,
            "regression_edge": regression_edge,
            "fit_quality": fit_quality,
            "volatility": volatility,
            "breakout_score": breakout_score,
            "flow_bias": flow_metrics["bias"],
            "depth_alpha": depth_alpha,
            "pressure_bias": pressure_bias,
            "hybrid_alpha": hybrid_alpha,
            "channel_position": float(channel_state["position"]),
            "channel_direction": float(channel_state["direction"]),
        }
        took_buy, took_sell = self.take_orders(
            regime,
            target_position,
            adjusted_fair,
            predicted_edge,
            fit_quality,
            volatility,
            depth_alpha,
            flow_metrics["bias"],
            breakout_score,
        )

        buy_quote, sell_quote = self.passive_quotes(
            adjusted_fair,
            regime,
            target_position,
            predicted_edge,
            fit_quality,
            volatility,
            breakout_score,
        )
        position = self.projected_position()

        if (
            not took_buy
            and buy_quote is not None
            and self.buy_capacity > 0
            and self.allow_passive("BUY", regime)
        ):
            if regime == "range" or position < target_position:
                quantity = min(self.passive_size("BUY", regime, volatility), self.buy_capacity)
                if regime != "range":
                    quantity = min(quantity, max(1, target_position - position))
                self.add_buy(buy_quote, quantity)

        position = self.projected_position()
        if (
            not took_sell
            and sell_quote is not None
            and self.sell_capacity > 0
            and self.allow_passive("SELL", regime)
        ):
            if regime == "range" or position > target_position:
                quantity = min(self.passive_size("SELL", regime, volatility), self.sell_capacity)
                if regime != "range":
                    quantity = min(quantity, max(1, position - target_position))
                self.add_sell(sell_quote, quantity)

        self.store_flow_metrics(flow_metrics)
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

    def load_trader_data(self, trader_data: str) -> Tuple[Dict[str, List[float]], Dict[str, dict]]:
        if not trader_data:
            return {}, {}
        try:
            parsed = json.loads(trader_data)
        except json.JSONDecodeError:
            return {}, {}

        raw_history = parsed.get("mid_history", {})
        if not isinstance(raw_history, dict):
            raw_history = {}

        cleaned: Dict[str, List[float]] = {}
        for product, values in raw_history.items():
            if isinstance(values, list):
                cleaned[product] = [float(value) for value in values[-BaseProductTrader.HISTORY_LENGTH :]]
        raw_memory = parsed.get("product_memory", {})
        cleaned_memory: Dict[str, dict] = {}
        if isinstance(raw_memory, dict):
            for product, value in raw_memory.items():
                if isinstance(value, dict):
                    cleaned_memory[product] = dict(value)
        return cleaned, cleaned_memory

    def build_trader_data(self, mid_history: Dict[str, List[float]], product_memory: Dict[str, dict]) -> str:
        return json.dumps(
            {"mid_history": mid_history, "product_memory": product_memory},
            separators=(",", ":"),
        )

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        mid_history, product_memory = self.load_trader_data(state.traderData)
        diagnostic_events: List[dict] = []

        for product in state.order_depths:
            if product not in self.PRODUCT_TRADERS:
                result[product] = []
                continue

            trader_class = self.PRODUCT_TRADERS[product]
            trader = trader_class(
                product,
                state,
                mid_history,
                product_memory,
                self.POSITION_LIMITS[product],
            )
            result[product] = trader.run()
            if getattr(trader, "diagnostic_events", None):
                diagnostic_events.extend(trader.diagnostic_events)

        conversions = 0
        trader_data = self.build_trader_data(mid_history, product_memory)
        if diagnostic_events:
            print(
                "DIAG "
                + json.dumps(
                    {
                        "ts": int(getattr(state, "timestamp", 0)),
                        "events": diagnostic_events,
                    },
                    separators=(",", ":"),
                )
            )
        return result, conversions, trader_data
