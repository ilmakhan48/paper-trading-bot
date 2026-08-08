from tradingbot.strategies.momentum import MomentumStrategy
from tradingbot.backtest.runner import run_backtest


def test_backtest_uptrend_strategy_passes():
    strat = MomentumStrategy(lookback=5, threshold=0.0)
    # steady uptrend: momentum strategy should catch it and profit
    closes = [100 + i for i in range(60)]
    result = run_backtest(strat, closes)
    assert result.strategy == "momentum"
    assert result.num_trades >= 2
    assert result.total_pnl > 0
    assert result.passed is True
    assert result.reason == "passed"


def test_backtest_flat_market_fails():
    strat = MomentumStrategy(lookback=5, threshold=0.0)
    closes = [100.0] * 60
    result = run_backtest(strat, closes)
    assert result.num_trades == 0
    assert result.passed is False
    assert "no trades" in result.reason.lower()


def test_backtest_result_has_drawdown_and_sharpe_fields():
    strat = MomentumStrategy(lookback=5, threshold=0.0)
    closes = [100 + i for i in range(60)]
    result = run_backtest(strat, closes)
    assert isinstance(result.sharpe, float)
    assert isinstance(result.max_drawdown, float)


def test_backtest_flat_market_has_no_trade_pnls():
    strat = MomentumStrategy(lookback=5, threshold=0.0)
    closes = [100.0] * 60
    result = run_backtest(strat, closes)
    assert result.trade_pnls == []


def test_backtest_uptrend_records_real_per_trade_pnl():
    # A strategy that only ever buys and rides a steady uptrend to the end should
    # record exactly one realized trade PnL (the forced final close), and it should
    # be a real winning trade rather than a placeholder number.
    strat = MomentumStrategy(lookback=5, threshold=0.0)
    closes = [100 + i for i in range(60)]
    result = run_backtest(strat, closes)
    assert len(result.trade_pnls) == result.num_trades // 2
    assert all(isinstance(p, float) for p in result.trade_pnls)
    # steady uptrend -> every round trip that gets held to a rising close should win
    assert sum(1 for p in result.trade_pnls if p > 0) >= 1


def test_backtest_choppy_market_produces_mixed_win_loss_trades():
    # A dip-then-rally produces one losing round trip followed by one winning round
    # trip, proving trade_pnls reflects real per-trade outcomes rather than a single
    # aggregate number derived from total_pnl.
    strat = MomentumStrategy(lookback=2, threshold=0.0)
    closes = [100, 110, 120, 90, 80, 70, 90, 110, 130, 150, 170, 140]
    result = run_backtest(strat, closes)
    assert len(result.trade_pnls) == result.num_trades // 2 == 2
    assert result.trade_pnls[0] < 0
    assert result.trade_pnls[1] > 0
