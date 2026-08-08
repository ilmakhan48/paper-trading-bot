from tradingbot.strategies.base import Strategy


def _sma(values: list[float], period: int) -> float:
    return sum(values[-period:]) / period


class SmaCrossStrategy(Strategy):
    name = "sma_cross"

    def __init__(self, fast: int = 10, slow: int = 30):
        self.fast = fast
        self.slow = slow

    def signal(self, closes: list[float]) -> str:
        if len(closes) < self.slow + 1:
            return "hold"
        fast_prev = _sma(closes[:-1], self.fast)
        slow_prev = _sma(closes[:-1], self.slow)
        fast_now = _sma(closes, self.fast)
        slow_now = _sma(closes, self.slow)
        if fast_prev <= slow_prev and fast_now > slow_now:
            return "buy"
        if fast_prev >= slow_prev and fast_now < slow_now:
            return "sell"
        return "hold"
