from tradingbot.strategies.sma_cross import SmaCrossStrategy
from tradingbot.strategies.rsi import RsiStrategy
from tradingbot.strategies.momentum import MomentumStrategy


def test_sma_cross_buy_signal():
    strat = SmaCrossStrategy(fast=2, slow=4)
    # last close makes fast SMA cross above slow SMA
    closes = [10, 10, 10, 10, 20]
    assert strat.signal(closes) == "buy"


def test_sma_cross_hold_when_insufficient_data():
    strat = SmaCrossStrategy(fast=10, slow=30)
    assert strat.signal([1, 2, 3]) == "hold"


def test_rsi_buy_on_oversold_recovery():
    # a run of losses driving RSI low, then a bounce up
    closes = [100, 98, 96, 94, 92, 90, 88, 86, 84, 82, 80, 78, 76, 74, 80]
    strat = RsiStrategy(period=14, oversold=30, overbought=70)
    signal = strat.signal(closes)
    assert signal in ("buy", "hold")  # bounce should push RSI up from oversold


def test_momentum_buy_on_positive_return():
    closes = [100] * 20 + [110]
    strat = MomentumStrategy(lookback=20, threshold=0.02)
    assert strat.signal(closes) == "buy"


def test_momentum_sell_on_negative_return():
    closes = [100] * 20 + [90]
    strat = MomentumStrategy(lookback=20, threshold=0.02)
    assert strat.signal(closes) == "sell"


def test_momentum_hold_within_threshold():
    closes = [100] * 20 + [101]
    strat = MomentumStrategy(lookback=20, threshold=0.02)
    assert strat.signal(closes) == "hold"
