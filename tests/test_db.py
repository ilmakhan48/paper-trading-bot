from tradingbot.engine.db import (
    init_db, insert_trade, close_trade, insert_equity_point,
    insert_strategy_run, get_open_trades, get_all_trades,
    get_equity_history, get_strategy_runs,
)


def test_insert_and_close_trade(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    trade_id = insert_trade(
        conn, symbol="BTCUSDT", side="buy", qty=0.01, price=60000.0,
        fee=0.6, slippage=0.05, strategy="sma_cross", opened_at="2026-07-05T00:00:00",
    )
    open_trades = get_open_trades(conn)
    assert len(open_trades) == 1
    assert open_trades[0]["id"] == trade_id
    assert open_trades[0]["closed_at"] is None

    close_trade(
        conn, trade_id, close_price=61000.0, fee=0.61,
        slippage=0.05, pnl=9.34, closed_at="2026-07-05T00:05:00",
    )
    assert get_open_trades(conn) == []
    all_trades = get_all_trades(conn)
    assert all_trades[0]["pnl"] == 9.34
    assert all_trades[0]["closed_at"] == "2026-07-05T00:05:00"


def test_equity_history(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    insert_equity_point(conn, timestamp="2026-07-05T00:00:00", equity=10000.0)
    insert_equity_point(conn, timestamp="2026-07-05T00:05:00", equity=10009.34)
    history = get_equity_history(conn)
    assert len(history) == 2
    assert history[-1]["equity"] == 10009.34


def test_strategy_runs(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    insert_strategy_run(
        conn, strategy="rsi", passed=False, sharpe=-0.3,
        max_drawdown=0.42, reason="Sharpe below 0 threshold",
    )
    runs = get_strategy_runs(conn)
    assert runs[0]["strategy"] == "rsi"
    assert runs[0]["passed"] is False
    assert runs[0]["reason"] == "Sharpe below 0 threshold"
