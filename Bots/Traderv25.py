from datamodel import OrderDepth, Order, TradingState
from typing import Any, Dict, List, Optional, Tuple
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
    "BASE_TAKE_EDGE": 1.10,
    "BASE_QUOTE_EDGE": 2.25,
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
    "ML_LEARNING_RATE": 0.16,
    "ML_WEIGHT_CLIP": 1.80,
    "ML_PRED_CLIP": 2.50,
    "ML_BLEND": 1.60,
    "ML_CONFIDENCE_MIN_SAMPLES": 12.0,
    "ML_CONFIDENCE_MAE_SCALE": 1.40,
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
        self.bid_wall: Optional[int] = None
        self.ask_wall: Optional[int] = None
        self.wall_mid: Optional[float] = None
        self.mid: Optional[float] = None
        self.micro: Optional[float] = None
        self.spread: Optional[int] = None
        self.recent_average: Optional[float] = None
        self.short_average: Optional[float] = None
        self.momentum: float = 0.0
        self.short_momentum: float = 0.0
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
        self.bid_wall = self.buy_levels[-1][0] if self.buy_levels else None
        self.ask_wall = self.sell_levels[-1][0] if self.sell_levels else None
        self.wall_mid = (self.bid_wall + self.ask_wall) / 2 if self.bid_wall is not None and self.ask_wall is not None else None
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
        short_history = history[-3:]
        self.short_average = sum(short_history) / len(short_history) if short_history else self.mid
        self.momentum = self.mid - self.recent_average
        self.short_momentum = self.mid - self.short_average

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
        model_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit)
        self.apply_parameter_overrides(self.PARAMETER_DEFAULTS, params)
        self.soft_limit = int(position_limit * self.SOFT_LIMIT_RATIO)
        self.model_state = self.clean_model_state(model_state)

    def default_model_state(self) -> Dict[str, Any]:
        return {
            "weights": [0.0] * 7,
            "prev_features": None,
            "prev_mid": None,
            "samples": 0,
            "mae_ema": 1.0,
            "dir_ema": 0.5,
        }

    def clean_model_state(self, model_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        cleaned = self.default_model_state()
        if not isinstance(model_state, dict):
            return cleaned

        raw_weights = model_state.get("weights")
        if isinstance(raw_weights, list) and len(raw_weights) == len(cleaned["weights"]):
            cleaned["weights"] = [
                max(-self.ML_WEIGHT_CLIP, min(self.ML_WEIGHT_CLIP, float(value)))
                for value in raw_weights
            ]

        raw_features = model_state.get("prev_features")
        if isinstance(raw_features, list) and len(raw_features) == len(cleaned["weights"]):
            cleaned["prev_features"] = [float(value) for value in raw_features]

        raw_prev_mid = model_state.get("prev_mid")
        if isinstance(raw_prev_mid, (int, float)):
            cleaned["prev_mid"] = float(raw_prev_mid)

        raw_samples = model_state.get("samples")
        if isinstance(raw_samples, (int, float)):
            cleaned["samples"] = max(0, int(raw_samples))

        raw_mae = model_state.get("mae_ema")
        if isinstance(raw_mae, (int, float)):
            cleaned["mae_ema"] = max(0.0, float(raw_mae))

        raw_dir = model_state.get("dir_ema")
        if isinstance(raw_dir, (int, float)):
            cleaned["dir_ema"] = max(0.0, min(1.0, float(raw_dir)))

        return cleaned

    def clipped_prediction(self, prediction: float) -> float:
        return max(-self.ML_PRED_CLIP, min(self.ML_PRED_CLIP, prediction))

    def ml_features(
        self,
        regression_edge: float,
        fit_quality: float,
    ) -> List[float]:
        spread_scale = max(1.0, float(self.spread))
        return [
            1.0,
            max(-1.5, min(1.5, (float(self.micro) - float(self.mid)) / spread_scale)),
            max(-1.5, min(1.5, self.short_momentum / 3.0)),
            max(-1.5, min(1.5, self.momentum / 6.0)),
            max(-1.0, min(1.0, self.imbalance)),
            max(-1.5, min(1.5, regression_edge / 3.0)),
            max(-1.0, min(1.0, (fit_quality - 0.5) * 2.0)),
        ]

    def ml_signal(
        self,
        features: List[float],
        volatility: float,
    ) -> Tuple[float, float]:
        weights = [float(value) for value in self.model_state["weights"]]
        prev_features = self.model_state.get("prev_features")
        prev_mid = self.model_state.get("prev_mid")
        samples = int(self.model_state.get("samples", 0))
        mae_ema = float(self.model_state.get("mae_ema", 1.0))
        dir_ema = float(self.model_state.get("dir_ema", 0.5))

        if (
            isinstance(prev_features, list)
            and len(prev_features) == len(weights)
            and isinstance(prev_mid, (int, float))
        ):
            previous_prediction = self.clipped_prediction(
                sum(weight * value for weight, value in zip(weights, prev_features))
            )
            realized_delta = float(self.mid) - float(prev_mid)
            error = realized_delta - previous_prediction
            learning_rate = self.ML_LEARNING_RATE / (1.0 + (0.25 * abs(error)))

            updated_weights: List[float] = []
            for weight, value in zip(weights, prev_features):
                candidate = weight + (learning_rate * error * value)
                updated_weights.append(
                    max(-self.ML_WEIGHT_CLIP, min(self.ML_WEIGHT_CLIP, candidate))
                )

            weights = updated_weights
            samples += 1
            mae_ema = (0.90 * mae_ema) + (0.10 * abs(error))
            hit = 0.5
            if abs(previous_prediction) >= 0.15:
                hit = 1.0 if (previous_prediction * realized_delta) > 0 else 0.0
            dir_ema = (0.90 * dir_ema) + (0.10 * hit)

        current_prediction = self.clipped_prediction(
            sum(weight * value for weight, value in zip(weights, features))
        )
        sample_factor = min(1.0, samples / self.ML_CONFIDENCE_MIN_SAMPLES)
        error_factor = max(0.0, min(1.0, 1.0 - (mae_ema / self.ML_CONFIDENCE_MAE_SCALE)))
        direction_factor = 0.5 + (0.5 * dir_ema)
        volatility_factor = 0.75 if volatility >= self.TOXIC_VOLATILITY_THRESHOLD else 1.0
        confidence = sample_factor * error_factor * direction_factor * volatility_factor

        self.model_state["weights"] = weights
        self.model_state["prev_features"] = [float(value) for value in features]
        self.model_state["prev_mid"] = float(self.mid)
        self.model_state["samples"] = samples
        self.model_state["mae_ema"] = mae_ema
        self.model_state["dir_ema"] = dir_ema

        return current_prediction, max(0.0, min(1.0, confidence))

    def regression_metrics(self) -> Tuple[float, float, float, float, float]:
        history = self.mid_history.get(self.product, [])
        window = history[-int(self.REGRESSION_WINDOW) :]
        if len(window) < 2:
            return 0.0, float(self.mid), float(self.mid), 0.0, 0.0

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
        return slope, predicted_now, predicted_next, fit_quality, volatility

    def classify_state(
        self,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
    ) -> str:
        if float(self.spread) >= self.TOXIC_SPREAD_THRESHOLD and volatility >= self.TOXIC_VOLATILITY_THRESHOLD:
            return "volatile"
        if (
            predicted_edge >= self.TREND_EDGE_THRESHOLD
            and fit_quality >= self.FIT_THRESHOLD
            and self.imbalance >= self.TREND_IMBALANCE_THRESHOLD
            and self.momentum >= 0.75
            and float(self.micro) >= float(self.mid)
        ):
            return "trend_up"
        if (
            predicted_edge <= -self.TREND_EDGE_THRESHOLD
            and fit_quality >= self.FIT_THRESHOLD
            and self.imbalance <= -self.TREND_IMBALANCE_THRESHOLD
            and self.momentum <= -0.75
            and float(self.micro) <= float(self.mid)
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
    ) -> float:
        line_gap = predicted_now - float(self.mid)
        fair = (
            self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
            + self.HISTORY_WEIGHT * float(self.recent_average)
            + self.REGRESSION_WEIGHT * predicted_next
            + self.IMBALANCE_WEIGHT * self.imbalance
        )
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
    ) -> float:
        fair = self.fair_value(regime, target_position, predicted_now, predicted_next)
        return fair - (self.projected_position() * self.INVENTORY_SKEW)

    def take_edge(
        self,
        side: str,
        regime: str,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
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
            edge += -0.35 if side == "BUY" else 0.55
        elif regime == "trend_down":
            edge += -0.35 if side == "SELL" else 0.55
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

        return max(0.5, edge)

    def quote_edge(self, regime: str, volatility: float, fit_quality: float) -> float:
        edge = max(self.BASE_QUOTE_EDGE, float(self.spread) / 3.5)
        edge = min(self.MAX_QUOTE_EDGE, edge)

        if abs(self.projected_position()) >= self.soft_limit:
            edge += 0.5

        if regime == "volatile":
            edge += 1.0
        elif regime in {"trend_up", "trend_down"}:
            edge += 0.15 + (0.10 * fit_quality)

        edge += 0.20 * min(2.0, volatility)
        return min(self.MAX_QUOTE_EDGE, edge)

    def passive_quotes(
        self,
        adjusted_fair: float,
        regime: str,
        target_position: int,
        predicted_edge: float,
        fit_quality: float,
        volatility: float,
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
    ) -> Tuple[bool, bool]:
        took_buy = False
        took_sell = False

        if (
            int(self.best_ask) <= adjusted_fair - self.take_edge("BUY", regime, predicted_edge, fit_quality, volatility)
            and self.buy_capacity > 0
        ):
            take_limit = self.MAX_TAKE_SIZE + (int(self.TREND_ENTRY_TAKE_BONUS) if regime == "trend_up" else 0)
            if regime != "range" and self.projected_position() >= target_position:
                pass
            else:
                quantity = min(self.best_ask_volume, take_limit)
                if regime != "range":
                    quantity = min(quantity, max(1, target_position - self.projected_position()))
                before = self.buy_capacity
                self.add_buy(int(self.best_ask), quantity)
                took_buy = self.buy_capacity < before

        if (
            int(self.best_bid) >= adjusted_fair + self.take_edge("SELL", regime, predicted_edge, fit_quality, volatility)
            and self.sell_capacity > 0
        ):
            take_limit = self.MAX_TAKE_SIZE + (int(self.TREND_ENTRY_TAKE_BONUS) if regime == "trend_down" else 0)
            required_bonus = 0.0
            if regime == "trend_up" and predicted_edge >= self.TREND_EDGE_THRESHOLD:
                required_bonus += self.TREND_HOLD_EXIT_BONUS
            if regime == "trend_up" and predicted_edge >= self.STRONG_TREND_EDGE:
                required_bonus += self.STRONG_TREND_HOLD_EXIT_BONUS
            if regime != "range" and self.projected_position() <= target_position:
                pass
            elif int(self.best_bid) < adjusted_fair + self.take_edge("SELL", regime, predicted_edge, fit_quality, volatility) + required_bonus:
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

        _slope, predicted_now, predicted_next, fit_quality, volatility = self.regression_metrics()
        regression_edge = predicted_next - float(self.mid)
        ml_prediction, ml_confidence = self.ml_signal(
            self.ml_features(regression_edge, fit_quality),
            volatility,
        )
        ml_weight = self.ML_BLEND * ml_confidence * (0.35 + max(0.0, 0.60 - fit_quality))
        blended_next = predicted_next + (ml_weight * ml_prediction)
        predicted_edge = blended_next - float(self.mid)
        effective_fit = min(1.0, fit_quality + (0.25 * ml_confidence))
        regime = self.classify_state(predicted_edge, effective_fit, volatility)
        target_position = self.target_position(regime, predicted_edge, effective_fit)
        adjusted_fair = self.adjusted_fair_value(regime, target_position, predicted_now, blended_next)
        took_buy, took_sell = self.take_orders(
            regime,
            target_position,
            adjusted_fair,
            predicted_edge,
            effective_fit,
            volatility,
        )

        buy_quote, sell_quote = self.passive_quotes(
            adjusted_fair,
            regime,
            target_position,
            predicted_edge,
            effective_fit,
            volatility,
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

    def load_trader_data(self, trader_data: str) -> Tuple[Dict[str, List[float]], Dict[str, Any]]:
        if not trader_data:
            return {}, {}
        try:
            parsed = json.loads(trader_data)
        except json.JSONDecodeError:
            return {}, {}

        raw_history = parsed.get("mid_history", {})
        if not isinstance(raw_history, dict):
            return {}, {}

        cleaned: Dict[str, List[float]] = {}
        for product, values in raw_history.items():
            if isinstance(values, list):
                cleaned[product] = [float(value) for value in values[-BaseProductTrader.HISTORY_LENGTH :]]
        raw_model_state = parsed.get("tomatoes_ml", {})
        model_state = raw_model_state if isinstance(raw_model_state, dict) else {}
        return cleaned, model_state

    def build_trader_data(
        self,
        mid_history: Dict[str, List[float]],
        tomatoes_ml: Dict[str, Any],
    ) -> str:
        return json.dumps(
            {"mid_history": mid_history, "tomatoes_ml": tomatoes_ml},
            separators=(",", ":"),
        )

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        mid_history, tomatoes_ml = self.load_trader_data(state.traderData)

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
                    model_state=tomatoes_ml,
                )
            else:
                trader = trader_class(
                    product,
                    state,
                    mid_history,
                    self.POSITION_LIMITS[product],
                )
            result[product] = trader.run()

        conversions = 0
        trader_data = self.build_trader_data(mid_history, tomatoes_ml)
        return result, conversions, trader_data
