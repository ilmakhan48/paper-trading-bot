from tradingbot.strategies.base import Strategy


def _rsi(closes: list[float], period: int) -> float:
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    window = deltas[-period:]
    gains = [d for d in window if d > 0]
    losses = [-d for d in window if d < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


class RsiStrategy(Strategy):
    name = "rsi"

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def signal(self, closes: list[float]) -> str:
        if len(closes) < self.period + 2:
            return "hold"
        rsi_prev = _rsi(closes[:-1], self.period)
        rsi_now = _rsi(closes, self.period)
        if rsi_prev <= self.oversold and rsi_now > self.oversold:
            return "buy"
        if rsi_prev >= self.overbought and rsi_now < self.overbought:
            return "sell"
        return "hold"
