import pytest
from tradingbot.engine.portfolio import Portfolio
from tradingbot.engine.db import init_db, get_open_trades, get_all_trades
from tradingbot.engine.broker import Broker, TAKER_FEE_RATE, SLIPPAGE_RATE


def test_open_trade_applies_fee_and_unfavorable_slippage(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    portfolio = Portfolio(cash=10000.0)
    broker = Broker(portfolio, conn)

    trade_id = broker.open_trade(
        symbol="BTCUSDT", side="buy", qty=0.1, market_price=60000.0,
        strategy="sma_cross", opened_at="2026-07-05T00:00:00",
    )
    # buy slippage moves fill price UP (unfavorable to buyer)
    expected_fill = 60000.0 * (1 + SLIPPAGE_RATE)
    expected_fee = expected_fill * 0.1 * TAKER_FEE_RATE
    assert portfolio.positions["BTCUSDT"]["avg_price"] == pytest.approx(expected_fill)
    assert portfolio.cash == pytest.approx(10000.0 - expected_fill * 0.1 - expected_fee)
    open_trades = get_open_trades(conn)
    assert open_trades[0]["id"] == trade_id


def test_close_trade_truthful_loss(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    portfolio = Portfolio(cash=10000.0)
    broker = Broker(portfolio, conn)

    trade_id = broker.open_trade(
        symbol="BTCUSDT", side="buy", qty=0.1, market_price=60000.0,
        strategy="sma_cross", opened_at="2026-07-05T00:00:00",
    )
    # price drops hard — must record the real loss, not round it away
    pnl = broker.close_trade(
        trade_id, symbol="BTCUSDT", market_price=50000.0, closed_at="2026-07-05T00:05:00",
    )
    assert pnl < 0
    all_trades = get_all_trades(conn)
    closed = [t for t in all_trades if t["id"] == trade_id][0]
    assert closed["pnl"] == pytest.approx(pnl)
    assert closed["closed_at"] == "2026-07-05T00:05:00"
