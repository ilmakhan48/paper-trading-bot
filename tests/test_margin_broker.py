import pytest
from tradingbot.margin.portfolio import MarginPortfolio
from tradingbot.margin.db import init_margin_db, get_open_positions, get_all_positions
from tradingbot.margin.broker import MarginBroker


def test_open_position_writes_to_db(tmp_path):
    conn = init_margin_db(str(tmp_path / "m.db"))
    portfolio = MarginPortfolio(cash=1000.0)
    broker = MarginBroker(portfolio, conn)
    position_id = broker.open_position(
        symbol="BTCUSDT", side="long", qty=0.1, entry_price=100.0,
        leverage=10, opened_at="2026-07-05T00:00:00",
    )
    open_positions = get_open_positions(conn)
    assert open_positions[0]["id"] == position_id
    assert open_positions[0]["side"] == "long"


def test_apply_funding_updates_db(tmp_path):
    conn = init_margin_db(str(tmp_path / "m.db"))
    portfolio = MarginPortfolio(cash=1000.0)
    broker = MarginBroker(portfolio, conn)
    broker.open_position(
        symbol="BTCUSDT", side="long", qty=1.0, entry_price=100.0,
        leverage=10, opened_at="2026-07-05T00:00:00",
    )
    broker.apply_funding("BTCUSDT", funding_rate=0.0001, mark_price=100.0)
    positions = get_open_positions(conn)
    assert positions[0]["funding_paid"] == pytest.approx(-0.01)


def test_close_position_writes_pnl_to_db(tmp_path):
    conn = init_margin_db(str(tmp_path / "m.db"))
    portfolio = MarginPortfolio(cash=1000.0)
    broker = MarginBroker(portfolio, conn)
    broker.open_position(
        symbol="BTCUSDT", side="long", qty=1.0, entry_price=100.0,
        leverage=10, opened_at="2026-07-05T00:00:00",
    )
    pnl = broker.close_position("BTCUSDT", close_price=110.0, closed_at="2026-07-05T00:05:00")
    assert pnl == pytest.approx(10.0)
    assert get_open_positions(conn) == []
    all_positions = get_all_positions(conn)
    assert all_positions[0]["pnl"] == pytest.approx(10.0)
    assert all_positions[0]["liquidated"] is False


def test_check_liquidation_force_closes_breached_long(tmp_path):
    conn = init_margin_db(str(tmp_path / "m.db"))
    portfolio = MarginPortfolio(cash=1000.0)
    broker = MarginBroker(portfolio, conn)
    broker.open_position(
        symbol="BTCUSDT", side="long", qty=1.0, entry_price=100.0,
        leverage=10, opened_at="2026-07-05T00:00:00",
    )
    liq_price = portfolio.positions["BTCUSDT"].liquidation_price
    liquidated = broker.check_liquidation(
        "BTCUSDT", mark_price=liq_price - 1, closed_at="2026-07-05T00:01:00",
    )
    assert liquidated is True
    assert "BTCUSDT" not in portfolio.positions
    all_positions = get_all_positions(conn)
    assert all_positions[0]["liquidated"] is True
    assert all_positions[0]["close_price"] == pytest.approx(liq_price)


def test_check_liquidation_force_closes_breached_short(tmp_path):
    conn = init_margin_db(str(tmp_path / "m.db"))
    portfolio = MarginPortfolio(cash=1000.0)
    broker = MarginBroker(portfolio, conn)
    broker.open_position(
        symbol="BTCUSDT", side="short", qty=1.0, entry_price=100.0,
        leverage=10, opened_at="2026-07-05T00:00:00",
    )
    liq_price = portfolio.positions["BTCUSDT"].liquidation_price
    liquidated = broker.check_liquidation(
        "BTCUSDT", mark_price=liq_price + 1, closed_at="2026-07-05T00:01:00",
    )
    assert liquidated is True
    assert "BTCUSDT" not in portfolio.positions
    all_positions = get_all_positions(conn)
    assert all_positions[0]["liquidated"] is True
    assert all_positions[0]["close_price"] == pytest.approx(liq_price)


def test_check_liquidation_no_breach_returns_false(tmp_path):
    conn = init_margin_db(str(tmp_path / "m.db"))
    portfolio = MarginPortfolio(cash=1000.0)
    broker = MarginBroker(portfolio, conn)
    broker.open_position(
        symbol="BTCUSDT", side="long", qty=1.0, entry_price=100.0,
        leverage=10, opened_at="2026-07-05T00:00:00",
    )
    liquidated = broker.check_liquidation("BTCUSDT", mark_price=105.0, closed_at="2026-07-05T00:01:00")
    assert liquidated is False
    assert "BTCUSDT" in portfolio.positions
