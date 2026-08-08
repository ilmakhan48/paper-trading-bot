from tradingbot.strategies.base import Strategy


class MomentumStrategy(Strategy):
    name = "momentum"

    def __init__(self, lookback: int = 20, threshold: float = 0.0):
        self.lookback = lookback
        self.threshold = threshold

    def signal(self, closes: list[float]) -> str:
        if len(closes) < self.lookback + 1:
            return "hold"
        past = closes[-(self.lookback + 1)]
        now = closes[-1]
        ret = (now - past) / past
        if ret > self.threshold:
            return "buy"
        if ret < -self.threshold:
            return "sell"
        return "hold"
