# tests/test_margin_portfolio.py
import pytest
from tradingbot.margin.portfolio import (
    MarginPortfolio, liquidation_price, InsufficientMarginError,
    PositionAlreadyClosedError, PositionAlreadyOpenError, MAINTENANCE_MARGIN_RATE,
)


def test_liquidation_price_long():
    price = liquidation_price(entry_price=100.0, leverage=10, side="long")
    assert price == pytest.approx(100.0 * (1 - 0.1 + MAINTENANCE_MARGIN_RATE))


def test_liquidation_price_short():
    price = liquidation_price(entry_price=100.0, leverage=10, side="short")
    assert price == pytest.approx(100.0 * (1 + 0.1 - MAINTENANCE_MARGIN_RATE))


def test_liquidation_price_invalid_side_raises():
    with pytest.raises(ValueError):
        liquidation_price(entry_price=100.0, leverage=10, side="sideways")


def test_open_position_deducts_margin():
    portfolio = MarginPortfolio(cash=1000.0)
    position = portfolio.open_position("BTCUSDT", "long", qty=0.1, entry_price=100.0, leverage=10)
    assert position.margin == pytest.approx(1.0)  # notional 10 / leverage 10
    assert portfolio.cash == pytest.approx(999.0)
    assert portfolio.positions["BTCUSDT"] is position


def test_open_position_insufficient_margin_raises():
    portfolio = MarginPortfolio(cash=0.5)
    with pytest.raises(InsufficientMarginError):
        portfolio.open_position("BTCUSDT", "long", qty=0.1, entry_price=100.0, leverage=10)


def test_apply_funding_long_pays_on_positive_rate():
    portfolio = MarginPortfolio(cash=1000.0)
    portfolio.open_position("BTCUSDT", "long", qty=1.0, entry_price=100.0, leverage=10)
    payment = portfolio.apply_funding("BTCUSDT", funding_rate=0.0001, mark_price=100.0)
    assert payment == pytest.approx(-0.01)
    assert portfolio.cash == pytest.approx(1000.0 - 10.0 - 0.01)


def test_apply_funding_short_receives_on_positive_rate():
    portfolio = MarginPortfolio(cash=1000.0)
    portfolio.open_position("BTCUSDT", "short", qty=1.0, entry_price=100.0, leverage=10)
    payment = portfolio.apply_funding("BTCUSDT", funding_rate=0.0001, mark_price=100.0)
    assert payment == pytest.approx(0.01)


def test_close_position_long_profit():
    portfolio = MarginPortfolio(cash=1000.0)
    portfolio.open_position("BTCUSDT", "long", qty=1.0, entry_price=100.0, leverage=10)
    pnl = portfolio.close_position("BTCUSDT", close_price=110.0)
    assert pnl == pytest.approx(10.0)
    assert "BTCUSDT" not in portfolio.positions
    assert portfolio.cash == pytest.approx(1000.0 - 10.0 + 10.0 + 10.0)


def test_close_position_short_profit():
    portfolio = MarginPortfolio(cash=1000.0)
    portfolio.open_position("BTCUSDT", "short", qty=1.0, entry_price=100.0, leverage=10)
    pnl = portfolio.close_position("BTCUSDT", close_price=90.0)
    assert pnl == pytest.approx(10.0)


def test_close_position_without_open_raises():
    portfolio = MarginPortfolio(cash=1000.0)
    with pytest.raises(PositionAlreadyClosedError):
        portfolio.close_position("BTCUSDT", close_price=100.0)


def test_open_position_twice_same_symbol_raises_and_leaves_state_untouched():
    portfolio = MarginPortfolio(cash=1000.0)
    original = portfolio.open_position(
        "BTCUSDT", "long", qty=0.1, entry_price=100.0, leverage=10
    )
    cash_after_first_open = portfolio.cash
    with pytest.raises(PositionAlreadyOpenError):
        portfolio.open_position(
            "BTCUSDT", "long", qty=0.5, entry_price=200.0, leverage=5
        )
    assert portfolio.positions["BTCUSDT"] is original
    assert portfolio.cash == pytest.approx(cash_after_first_open)
