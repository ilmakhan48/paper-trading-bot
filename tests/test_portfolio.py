import pytest
from tradingbot.engine.portfolio import (
    Portfolio, InsufficientFundsError, InsufficientPositionError,
)


def test_starting_state():
    p = Portfolio(cash=10000.0)
    assert p.cash == 10000.0
    assert p.positions == {}
    assert p.equity({"BTCUSDT": 60000.0}) == 10000.0


def test_apply_buy_reduces_cash_and_opens_position():
    p = Portfolio(cash=10000.0)
    p.apply_buy("BTCUSDT", qty=0.01, price=60000.0, fee=0.6)
    assert p.cash == pytest.approx(10000.0 - 600.0 - 0.6)
    assert p.positions["BTCUSDT"]["qty"] == 0.01
    assert p.positions["BTCUSDT"]["avg_price"] == 60000.0


def test_apply_buy_insufficient_funds_raises():
    p = Portfolio(cash=100.0)
    with pytest.raises(InsufficientFundsError):
        p.apply_buy("BTCUSDT", qty=1.0, price=60000.0, fee=60.0)


def test_apply_sell_realizes_pnl_and_closes_position():
    p = Portfolio(cash=10000.0)
    p.apply_buy("BTCUSDT", qty=0.01, price=60000.0, fee=0.6)
    pnl = p.apply_sell("BTCUSDT", qty=0.01, price=61000.0, fee=0.61)
    # gross proceeds 610 - close fee 0.61 - cost basis 600 - open fee 0.6
    assert pnl == pytest.approx(610.0 - 0.61 - 600.0 - 0.6)
    assert "BTCUSDT" not in p.positions


def test_apply_sell_without_position_raises():
    p = Portfolio(cash=10000.0)
    with pytest.raises(InsufficientPositionError):
        p.apply_sell("BTCUSDT", qty=0.01, price=61000.0, fee=0.61)


def test_equity_includes_open_position_value():
    p = Portfolio(cash=10000.0)
    p.apply_buy("BTCUSDT", qty=0.01, price=60000.0, fee=0.6)
    equity = p.equity({"BTCUSDT": 62000.0})
    assert equity == pytest.approx(p.cash + 0.01 * 62000.0)
