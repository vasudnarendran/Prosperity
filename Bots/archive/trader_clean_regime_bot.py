from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List, Optional, Tuple
import json
import math


EMERALDS_CONFIG = {
    "REFERENCE_PRICE": 10000.0,
    "REFERENCE_WEIGHT": 0.85,
    "MID_WEIGHT": 0.10,
    "MICRO_WEIGHT": 0.05,
    "INVENTORY_SKEW": 0.020,
    "BASE_QUOTE_EDGE": 2.0,
    "BASE_TAKE_EDGE": 1.0,
    "PASSIVE_SIZE": 10,
    "MAX_TAKE_SIZE": 18,
    "SOFT_LIMIT_RATIO": 0.65,
}

TOMATOES_CONFIG = {
    "EWMA_ALPHA": 0.22,
    "FILL_EWMA_ALPHA": 0.18,
    "INVENTORY_SKEW": 0.030,
    "BASE_QUOTE_EDGE": 2.4,
    "BASE_TAKE_EDGE": 0.85,
    "PASSIVE_SIZE": 8,
    "MAX_TAKE_SIZE": 12,
    "SOFT_LIMIT_RATIO": 0.60,
    "FAST_VOL_THRESHOLD": 2.4,
    "DEFENSIVE_VOL_THRESHOLD": 3.4,
    "LEAN_SCORE": 0.35,
    "STRONG_SCORE": 1.05,
    "ALPHA_TREND_WEIGHT": 0.90,
    "ALPHA_MICRO_WEIGHT": 0.90,
    "ALPHA_IMBALANCE_WEIGHT": 0.60,
    "MARKOUT_DELAY_TICKS": 400,
    "TIME_HORIZON_TICKS": 10000.0,
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class BaseProductTrader:
    HISTORY_LENGTH = 24

    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
        memory: Optional[Dict[str, object]] = None,
    ) -> None:
        self.product = product
        self.state = state
        self.mid_history = mid_history
        self.position_limit = position_limit
        self.memory: Dict[str, object] = dict(memory) if isinstance(memory, dict) else {}
        self.orders: List[Order] = []

        self.order_depth: Optional[OrderDepth] = state.order_depths.get(product)
        self.position = state.position.get(product, 0)
        self.buy_capacity = position_limit - self.position
        self.sell_capacity = position_limit + self.position

        self.buy_levels: List[Tuple[int, int]] = []
        self.sell_levels: List[Tuple[int, int]] = []
        self.best_bid: Optional[int] = None
        self.best_ask: Optional[int] = None
        self.best_bid_volume = 0
        self.best_ask_volume = 0
        self.mid: Optional[float] = None
        self.micro: Optional[float] = None
        self.spread: Optional[int] = None
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
            ((price, -qty) for price, qty in self.order_depth.sell_orders.items()),
            key=lambda item: item[0],
        )

        if not self.buy_levels or not self.sell_levels:
            return

        self.best_bid, self.best_bid_volume = self.buy_levels[0]
        self.best_ask, self.best_ask_volume = self.sell_levels[0]

        self.mid = (self.best_bid + self.best_ask) / 2.0
        self.spread = self.best_ask - self.best_bid

        top_vol = self.best_bid_volume + self.best_ask_volume
        if top_vol > 0:
            self.micro = (
                (self.best_bid * self.best_ask_volume) + (self.best_ask * self.best_bid_volume)
            ) / top_vol
            self.imbalance = (self.best_bid_volume - self.best_ask_volume) / top_vol
        else:
            self.micro = self.mid
            self.imbalance = 0.0

        history = self.mid_history.get(self.product, [])
        history.append(float(self.mid))
        self.mid_history[self.product] = history[-self.HISTORY_LENGTH :]

    def has_book(self) -> bool:
        return (
            self.best_bid is not None
            and self.best_ask is not None
            and self.mid is not None
            and self.micro is not None
            and self.spread is not None
        )

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

    def clamp_buy_quote(self, price: Optional[int]) -> Optional[int]:
        if not self.has_book() or price is None:
            return None
        candidate = max(int(price), int(self.best_bid) + 1)
        return candidate if candidate < int(self.best_ask) else None

    def clamp_sell_quote(self, price: Optional[int]) -> Optional[int]:
        if not self.has_book() or price is None:
            return None
        candidate = min(int(price), int(self.best_ask) - 1)
        return candidate if candidate > int(self.best_bid) else None

    def recent_volatility(self, window: int = 8) -> float:
        history = self.mid_history.get(self.product, [])
        if len(history) < 2:
            return 0.0
        sample = history[-window:]
        diffs = [abs(sample[i] - sample[i - 1]) for i in range(1, len(sample))]
        return sum(diffs) / len(diffs) if diffs else 0.0

    def export_memory(self) -> Dict[str, object]:
        return self.memory

    def run(self) -> List[Order]:
        return self.orders


class EmeraldsTrader(BaseProductTrader):
    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
        memory: Optional[Dict[str, object]] = None,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit, memory)
        for key, value in EMERALDS_CONFIG.items():
            setattr(self, key, value)
        self.soft_limit = int(self.position_limit * self.SOFT_LIMIT_RATIO)

    def fair_value(self) -> float:
        return (
            self.REFERENCE_WEIGHT * self.REFERENCE_PRICE
            + self.MID_WEIGHT * float(self.mid)
            + self.MICRO_WEIGHT * float(self.micro)
        )

    def reservation_price(self) -> float:
        vol = max(0.5, self.recent_volatility())
        return self.fair_value() - (self.projected_position() * self.INVENTORY_SKEW * vol)

    def passive_size(self, side: str) -> int:
        size = self.PASSIVE_SIZE
        pos = self.projected_position()
        if side == "BUY":
            if pos < -self.soft_limit:
                size += 4
            elif pos > self.soft_limit:
                size = max(2, size - 5)
        else:
            if pos > self.soft_limit:
                size += 4
            elif pos < -self.soft_limit:
                size = max(2, size - 5)
        return int(size)

    def sweep_book(self, side: str, threshold: float, limit_qty: int, max_levels: int = 2) -> bool:
        traded = False
        remaining = max(0, int(limit_qty))
        if remaining <= 0:
            return traded

        if side == "BUY":
            levels = self.sell_levels[:max_levels]
            for price, qty in levels:
                if price > threshold or remaining <= 0 or self.buy_capacity <= 0:
                    break
                clip = min(qty, remaining, self.buy_capacity)
                if clip > 0:
                    self.add_buy(price, clip)
                    remaining -= clip
                    traded = True
        else:
            levels = self.buy_levels[:max_levels]
            for price, qty in levels:
                if price < threshold or remaining <= 0 or self.sell_capacity <= 0:
                    break
                clip = min(qty, remaining, self.sell_capacity)
                if clip > 0:
                    self.add_sell(price, clip)
                    remaining -= clip
                    traded = True
        return traded

    def passive_quotes(self, reservation: float) -> None:
        quote_edge = max(self.BASE_QUOTE_EDGE, float(self.spread) / 2.0)
        pos = self.projected_position()
        shift = 0
        if pos > self.soft_limit:
            shift = -1
        elif pos < -self.soft_limit:
            shift = 1

        buy_price = self.clamp_buy_quote(math.floor(reservation - quote_edge + shift))
        sell_price = self.clamp_sell_quote(math.ceil(reservation + quote_edge + shift))

        if buy_price is not None and self.buy_capacity > 0:
            self.add_buy(buy_price, self.passive_size("BUY"))
        if sell_price is not None and self.sell_capacity > 0:
            self.add_sell(sell_price, self.passive_size("SELL"))

        if int(self.spread) >= 5:
            pos = self.projected_position()
            buy_price_2 = self.clamp_buy_quote((buy_price - 1) if buy_price is not None else None)
            sell_price_2 = self.clamp_sell_quote((sell_price + 1) if sell_price is not None else None)
            if buy_price_2 is not None and buy_price_2 != buy_price and pos < self.soft_limit and self.buy_capacity > 0:
                self.add_buy(buy_price_2, max(2, self.passive_size("BUY") // 2))
            if sell_price_2 is not None and sell_price_2 != sell_price and pos > -self.soft_limit and self.sell_capacity > 0:
                self.add_sell(sell_price_2, max(2, self.passive_size("SELL") // 2))

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        reservation = self.reservation_price()
        vol = self.recent_volatility()
        take_edge = self.BASE_TAKE_EDGE + (0.15 * vol)

        buy_take_qty = self.MAX_TAKE_SIZE
        sell_take_qty = self.MAX_TAKE_SIZE
        if self.projected_position() > self.soft_limit:
            buy_take_qty = max(4, self.MAX_TAKE_SIZE - 8)
            sell_take_qty += 6
        elif self.projected_position() < -self.soft_limit:
            sell_take_qty = max(4, self.MAX_TAKE_SIZE - 8)
            buy_take_qty += 6

        self.sweep_book("BUY", reservation - take_edge, buy_take_qty, max_levels=2)
        self.sweep_book("SELL", reservation + take_edge, sell_take_qty, max_levels=2)
        self.passive_quotes(reservation)
        return self.orders


class TomatoesTrader(BaseProductTrader):
    def __init__(
        self,
        product: str,
        state: TradingState,
        mid_history: Dict[str, List[float]],
        position_limit: int,
        memory: Optional[Dict[str, object]] = None,
    ) -> None:
        super().__init__(product, state, mid_history, position_limit, memory)
        for key, value in TOMATOES_CONFIG.items():
            setattr(self, key, value)
        self.soft_limit = int(self.position_limit * self.SOFT_LIMIT_RATIO)

        self.prev_mid = float(self.memory.get("prev_mid", self.mid or 0.0))
        self.ewma_mid = float(self.memory.get("ewma_mid", self.mid or 0.0))
        self.ewma_return = float(self.memory.get("ewma_return", 0.0))
        self.ewma_abs_return = float(self.memory.get("ewma_abs_return", 0.0))
        self.ewma_micro_gap = float(self.memory.get("ewma_micro_gap", 0.0))
        self.ewma_imbalance = float(self.memory.get("ewma_imbalance", 0.0))
        self.regime_score = float(self.memory.get("regime_score", 0.0))
        self.mode = str(self.memory.get("mode", "neutral"))
        self.fill_quality = float(self.memory.get("fill_quality", 0.0))
        self.adverse = float(self.memory.get("adverse", 0.0))

        pending = self.memory.get("pending_fills", [])
        self.pending_fills: List[Dict[str, float]] = []
        if isinstance(pending, list):
            for item in pending:
                if isinstance(item, dict):
                    try:
                        self.pending_fills.append(
                            {
                                "timestamp": float(item.get("timestamp", 0.0)),
                                "price": float(item.get("price", 0.0)),
                                "side": float(item.get("side", 0.0)),
                                "qty": float(item.get("qty", 0.0)),
                            }
                        )
                    except (TypeError, ValueError):
                        continue

        seen_raw = self.memory.get("seen_trade_keys", [])
        self.seen_trade_keys = [str(x) for x in seen_raw[-32:]] if isinstance(seen_raw, list) else []

    def update_state(self) -> None:
        alpha = self.EWMA_ALPHA
        mid = float(self.mid)
        micro_gap = float(self.micro) - mid
        ret = mid - self.prev_mid

        self.ewma_mid = (1.0 - alpha) * self.ewma_mid + alpha * mid
        self.ewma_return = (1.0 - alpha) * self.ewma_return + alpha * ret
        self.ewma_abs_return = (1.0 - alpha) * self.ewma_abs_return + alpha * abs(ret)
        self.ewma_micro_gap = (1.0 - alpha) * self.ewma_micro_gap + alpha * micro_gap
        self.ewma_imbalance = (1.0 - alpha) * self.ewma_imbalance + alpha * self.imbalance
        self.prev_mid = mid

    def _trade_key(self, trade: object) -> str:
        timestamp = int(getattr(trade, "timestamp", -1))
        price = int(getattr(trade, "price", 0))
        quantity = int(getattr(trade, "quantity", 0))
        buyer = "1" if getattr(trade, "buyer", None) == "SUBMISSION" else "0"
        seller = "1" if getattr(trade, "seller", None) == "SUBMISSION" else "0"
        return f"{timestamp}:{price}:{quantity}:{buyer}:{seller}"

    def update_fill_feedback(self) -> None:
        current_ts = float(getattr(self.state, "timestamp", 0))
        spread_scale = max(1.0, float(self.spread) / 2.0)
        still_pending: List[Dict[str, float]] = []

        for fill in self.pending_fills:
            if current_ts - fill["timestamp"] < self.MARKOUT_DELAY_TICKS:
                still_pending.append(fill)
                continue

            signed_markout = (float(self.mid) - fill["price"]) * fill["side"]
            scaled_markout = clamp(signed_markout / spread_scale, -2.0, 2.0)
            weight = clamp(fill["qty"] / 6.0, 0.5, 2.0)
            a = clamp(self.FILL_EWMA_ALPHA * weight, 0.05, 0.35)

            self.fill_quality = (1.0 - a) * self.fill_quality + a * scaled_markout
            adverse_obs = 1.0 if signed_markout < -0.5 else 0.0
            self.adverse = (1.0 - a) * self.adverse + a * adverse_obs

        self.pending_fills = still_pending

        for trade in self.state.own_trades.get(self.product, []):
            key = self._trade_key(trade)
            if key in self.seen_trade_keys:
                continue
            self.seen_trade_keys.append(key)

            qty = max(1, abs(int(getattr(trade, "quantity", 0))))
            if getattr(trade, "buyer", None) == "SUBMISSION":
                side = 1.0
            elif getattr(trade, "seller", None) == "SUBMISSION":
                side = -1.0
            else:
                continue

            self.pending_fills.append(
                {
                    "timestamp": float(getattr(trade, "timestamp", 0)),
                    "price": float(getattr(trade, "price", 0)),
                    "side": side,
                    "qty": float(qty),
                }
            )

        self.seen_trade_keys = self.seen_trade_keys[-32:]

    def time_remaining(self) -> float:
        timestamp = float(getattr(self.state, "timestamp", 0))
        ticks = timestamp / 100.0
        return clamp((self.TIME_HORIZON_TICKS - ticks) / self.TIME_HORIZON_TICKS, 0.0, 1.0)

    def alpha_score(self) -> float:
        scale = max(0.5, self.ewma_abs_return)
        raw = (
            self.ALPHA_TREND_WEIGHT * (self.ewma_return / scale)
            + self.ALPHA_MICRO_WEIGHT * (self.ewma_micro_gap / scale)
            + self.ALPHA_IMBALANCE_WEIGHT * self.ewma_imbalance
        )
        self.regime_score = 0.75 * self.regime_score + 0.25 * raw
        return clamp(self.regime_score, -3.0, 3.0)

    def classify_mode(self, score: float) -> str:
        prev = self.mode
        if self.adverse > 0.70:
            return "defensive"
        if self.ewma_abs_return >= self.DEFENSIVE_VOL_THRESHOLD and abs(score) < self.LEAN_SCORE:
            return "defensive"

        enter_lean = self.LEAN_SCORE
        exit_lean = self.LEAN_SCORE * 0.60
        enter_strong = self.STRONG_SCORE
        exit_strong = self.STRONG_SCORE * 0.75

        if prev == "strong_up":
            if score >= exit_strong:
                return "strong_up"
        elif prev == "lean_up":
            if score >= exit_lean:
                return "lean_up"
        elif prev == "strong_down":
            if score <= -exit_strong:
                return "strong_down"
        elif prev == "lean_down":
            if score <= -exit_lean:
                return "lean_down"

        if score >= enter_strong:
            return "strong_up"
        if score >= enter_lean:
            return "lean_up"
        if score <= -enter_strong:
            return "strong_down"
        if score <= -enter_lean:
            return "lean_down"
        return "neutral"

    def target_position(self, mode: str, score: float) -> int:
        remaining = self.time_remaining()
        late_scale = 0.5 + (0.5 * remaining)
        max_target = int(self.soft_limit * late_scale)

        if mode == "strong_up":
            target = int(max_target * 0.75)
        elif mode == "lean_up":
            target = int(max_target * 0.40)
        elif mode == "strong_down":
            target = -int(max_target * 0.75)
        elif mode == "lean_down":
            target = -int(max_target * 0.40)
        else:
            target = 0

        if mode == "defensive":
            target = 0

        if self.adverse > 0.45:
            target = int(round(target * 0.6))
        return int(clamp(target, -self.soft_limit, self.soft_limit))

    def base_fair_value(self, score: float) -> float:
        half_spread = max(1.0, float(self.spread) / 2.0)
        flow_term = float(self.mid) + (half_spread * self.ewma_imbalance)
        trend_term = self.ewma_mid + self.ewma_return

        return (
            0.35 * float(self.mid)
            + 0.25 * self.ewma_mid
            + 0.20 * float(self.micro)
            + 0.10 * flow_term
            + 0.10 * trend_term
        )

    def reservation_price(self, target_position: int, score: float) -> float:
        fair = self.base_fair_value(score)
        pos = self.projected_position()
        vol_scale = max(0.7, 0.8 + self.ewma_abs_return)
        time_scale = 0.35 + self.time_remaining()
        inventory_gap = pos - target_position
        reservation = fair - (inventory_gap * self.INVENTORY_SKEW * vol_scale * time_scale)
        reservation += 0.35 * self.ewma_return
        reservation += 0.20 * self.ewma_micro_gap
        return reservation

    def take_edge(self, side: str, mode: str) -> float:
        edge = self.BASE_TAKE_EDGE + (0.25 * self.ewma_abs_return) + (0.20 * self.adverse)
        pos = self.projected_position()

        if side == "BUY":
            if pos > self.soft_limit:
                edge += 0.5
            elif pos < -self.soft_limit:
                edge -= 0.2
        else:
            if pos < -self.soft_limit:
                edge += 0.5
            elif pos > self.soft_limit:
                edge -= 0.2

        if mode in {"strong_up", "strong_down"}:
            if (mode == "strong_up" and side == "BUY") or (mode == "strong_down" and side == "SELL"):
                edge -= 0.25
            else:
                edge += 0.55
        elif mode in {"lean_up", "lean_down"}:
            if (mode == "lean_up" and side == "BUY") or (mode == "lean_down" and side == "SELL"):
                edge -= 0.10
            else:
                edge += 0.35

        if self.fill_quality > 0.25 and self.adverse < 0.35:
            edge -= 0.08
        return max(0.45, edge)

    def quote_edge(self, side: str, mode: str) -> float:
        edge = self.BASE_QUOTE_EDGE + max(0.0, float(self.spread) / 3.0 - 1.0)
        edge += 0.35 * self.ewma_abs_return + 0.35 * self.adverse

        favorable_buy = mode in {"lean_up", "strong_up"} and side == "BUY"
        favorable_sell = mode in {"lean_down", "strong_down"} and side == "SELL"
        unfavorable_buy = mode in {"lean_down", "strong_down"} and side == "BUY"
        unfavorable_sell = mode in {"lean_up", "strong_up"} and side == "SELL"

        if favorable_buy or favorable_sell:
            edge -= 0.60 if "strong" in mode else 0.30
        if unfavorable_buy or unfavorable_sell:
            edge += 1.10 if "strong" in mode else 0.55

        if mode == "defensive":
            edge += 1.0
        return max(1.0, edge)

    def passive_size(self, side: str, mode: str, target_position: int) -> int:
        size = self.PASSIVE_SIZE
        pos = self.projected_position()
        distance = abs(pos - target_position) / max(1, self.soft_limit)

        if mode == "defensive":
            size = max(1, size - 4)
        elif "strong" in mode:
            size += 2

        helps = (side == "BUY" and pos < target_position) or (side == "SELL" and pos > target_position)
        if helps:
            size += 2
        else:
            size = max(1, size - int(round(3.0 * distance)))

        if self.adverse > 0.45:
            size = max(1, size - 2)
        return int(size)

    def allow_side(self, side: str, mode: str, target_position: int) -> bool:
        pos = self.projected_position()

        if side == "BUY" and pos >= self.position_limit:
            return False
        if side == "SELL" and pos <= -self.position_limit:
            return False

        if mode == "neutral":
            return True

        if mode == "defensive":
            if abs(pos) <= 2:
                return False
            return (side == "SELL" and pos > 0) or (side == "BUY" and pos < 0)

        if mode == "lean_up":
            if side == "BUY":
                return True
            return pos > max(4, target_position // 2)

        if mode == "strong_up":
            if side == "BUY":
                return True
            return pos > target_position + 8

        if mode == "lean_down":
            if side == "SELL":
                return True
            return pos < min(-4, target_position // 2)

        if mode == "strong_down":
            if side == "SELL":
                return True
            return pos < target_position - 8

        return True

    def quote_price(self, side: str, reservation: float, mode: str) -> Optional[int]:
        edge = self.quote_edge(side, mode)
        if side == "BUY":
            base = math.floor(reservation - edge)
            if mode in {"lean_up", "strong_up"}:
                base += 1
            return self.clamp_buy_quote(base)
        base = math.ceil(reservation + edge)
        if mode in {"lean_down", "strong_down"}:
            base -= 1
        return self.clamp_sell_quote(base)

    def layered_passive_quotes(self, reservation: float, mode: str, target_position: int) -> None:
        placed_buy: List[int] = []
        placed_sell: List[int] = []

        if self.allow_side("BUY", mode, target_position) and self.buy_capacity > 0:
            p1 = self.quote_price("BUY", reservation, mode)
            if p1 is not None:
                self.add_buy(p1, self.passive_size("BUY", mode, target_position))
                placed_buy.append(p1)

            if int(self.spread) >= 4 and self.buy_capacity > 0 and mode != "defensive":
                p2 = self.clamp_buy_quote((p1 - 1) if p1 is not None else None)
                if p2 is not None and p2 not in placed_buy:
                    self.add_buy(p2, max(1, self.passive_size("BUY", mode, target_position) // 2))

        if self.allow_side("SELL", mode, target_position) and self.sell_capacity > 0:
            p1 = self.quote_price("SELL", reservation, mode)
            if p1 is not None:
                self.add_sell(p1, self.passive_size("SELL", mode, target_position))
                placed_sell.append(p1)

            if int(self.spread) >= 4 and self.sell_capacity > 0 and mode != "defensive":
                p2 = self.clamp_sell_quote((p1 + 1) if p1 is not None else None)
                if p2 is not None and p2 not in placed_sell:
                    self.add_sell(p2, max(1, self.passive_size("SELL", mode, target_position) // 2))

    def sweep_book(self, side: str, threshold: float, max_qty: int, max_levels: int = 3) -> bool:
        traded = False
        remaining = max(0, int(max_qty))
        if remaining <= 0:
            return traded

        if side == "BUY":
            for price, qty in self.sell_levels[:max_levels]:
                if price > threshold or remaining <= 0 or self.buy_capacity <= 0:
                    break
                clip = min(qty, remaining, self.buy_capacity)
                if clip > 0:
                    self.add_buy(price, clip)
                    traded = True
                    remaining -= clip
        else:
            for price, qty in self.buy_levels[:max_levels]:
                if price < threshold or remaining <= 0 or self.sell_capacity <= 0:
                    break
                clip = min(qty, remaining, self.sell_capacity)
                if clip > 0:
                    self.add_sell(price, clip)
                    traded = True
                    remaining -= clip
        return traded

    def aggressive_logic(self, reservation: float, mode: str, target_position: int) -> None:
        pos = self.projected_position()

        buy_need = max(0, target_position - pos)
        sell_need = max(0, pos - target_position)

        buy_qty = min(self.MAX_TAKE_SIZE, buy_need if mode != "neutral" else self.MAX_TAKE_SIZE // 2)
        sell_qty = min(self.MAX_TAKE_SIZE, sell_need if mode != "neutral" else self.MAX_TAKE_SIZE // 2)

        if self.allow_side("BUY", mode, target_position) and buy_qty > 0:
            threshold = reservation - self.take_edge("BUY", mode)
            if self.fill_quality > 0.25 and self.adverse < 0.35:
                buy_qty += 2
            self.sweep_book("BUY", threshold, buy_qty, max_levels=3)

        if self.allow_side("SELL", mode, target_position) and sell_qty > 0:
            threshold = reservation + self.take_edge("SELL", mode)
            if self.fill_quality > 0.25 and self.adverse < 0.35:
                sell_qty += 2
            self.sweep_book("SELL", threshold, sell_qty, max_levels=3)

        if mode == "defensive":
            pos = self.projected_position()
            if pos > 0 and self.sell_capacity > 0 and int(self.best_bid) >= math.floor(reservation):
                self.add_sell(int(self.best_bid), min(self.sell_capacity, min(pos, self.MAX_TAKE_SIZE)))
            elif pos < 0 and self.buy_capacity > 0 and int(self.best_ask) <= math.ceil(reservation):
                self.add_buy(int(self.best_ask), min(self.buy_capacity, min(abs(pos), self.MAX_TAKE_SIZE)))

    def run(self) -> List[Order]:
        if not self.has_book():
            return self.orders

        self.update_state()
        self.update_fill_feedback()

        score = self.alpha_score()
        mode = self.classify_mode(score)
        self.mode = mode
        target = self.target_position(mode, score)
        reservation = self.reservation_price(target, score)

        self.aggressive_logic(reservation, mode, target)
        self.layered_passive_quotes(reservation, mode, target)

        self.memory = {
            "prev_mid": round(self.prev_mid, 4),
            "ewma_mid": round(self.ewma_mid, 4),
            "ewma_return": round(self.ewma_return, 4),
            "ewma_abs_return": round(self.ewma_abs_return, 4),
            "ewma_micro_gap": round(self.ewma_micro_gap, 4),
            "ewma_imbalance": round(self.ewma_imbalance, 4),
            "regime_score": round(self.regime_score, 4),
            "mode": self.mode,
            "fill_quality": round(self.fill_quality, 4),
            "adverse": round(self.adverse, 4),
            "pending_fills": [
                {
                    "timestamp": round(fill["timestamp"], 1),
                    "price": round(fill["price"], 1),
                    "side": round(fill["side"], 1),
                    "qty": round(fill["qty"], 1),
                }
                for fill in self.pending_fills[-10:]
            ],
            "seen_trade_keys": self.seen_trade_keys[-32:],
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

    def load_trader_data(
        self, trader_data: str
    ) -> Tuple[Dict[str, List[float]], Dict[str, Dict[str, object]]]:
        if not trader_data:
            return {}, {}
        try:
            parsed = json.loads(trader_data)
        except json.JSONDecodeError:
            return {}, {}

        raw_history = parsed.get("mid_history", {})
        cleaned_history: Dict[str, List[float]] = {}
        if isinstance(raw_history, dict):
            for product, values in raw_history.items():
                if isinstance(values, list):
                    cleaned_history[product] = [
                        float(v) for v in values[-BaseProductTrader.HISTORY_LENGTH :]
                    ]

        raw_memory = parsed.get("memory", {})
        cleaned_memory: Dict[str, Dict[str, object]] = {}
        if isinstance(raw_memory, dict):
            for product, values in raw_memory.items():
                if isinstance(values, dict):
                    cleaned_memory[product] = values
        return cleaned_history, cleaned_memory

    def build_trader_data(
        self,
        mid_history: Dict[str, List[float]],
        memory: Dict[str, Dict[str, object]],
    ) -> str:
        return json.dumps(
            {"mid_history": mid_history, "memory": memory},
            separators=(",", ":"),
        )

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        mid_history, memory = self.load_trader_data(state.traderData)
        next_memory: Dict[str, Dict[str, object]] = dict(memory)

        for product in state.order_depths:
            trader_class = self.PRODUCT_TRADERS.get(product)
            if trader_class is None:
                result[product] = []
                continue

            trader = trader_class(
                product=product,
                state=state,
                mid_history=mid_history,
                position_limit=self.POSITION_LIMITS[product],
                memory=memory.get(product, {}),
            )
            result[product] = trader.run()
            exported = trader.export_memory()
            if exported:
                next_memory[product] = exported

        conversions = 0
        trader_data = self.build_trader_data(mid_history, next_memory)
        return result, conversions, trader_data
