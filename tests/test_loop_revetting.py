# tests/test_loop_revetting.py
import pytest
import requests

from tradingbot.data.binance_feed import PriceFetchError
from tradingbot.engine.db import init_db, insert_trade
from tradingbot.loop.main import (
    maybe_revet, _demoted_with_open_positions, REVET_INTERVAL_CYCLES, ALL_STRATEGIES,
)


def test_maybe_revet_does_not_trigger_before_interval():
    calls = []

    def fake_vet_fn(conn):
        calls.append(conn)
        return ([("BTCUSDT", ALL_STRATEGIES[0], 0.5, 1.5)], {})

    approved = [("ETHUSDT", ALL_STRATEGIES[1], 0.4, 1.2)]
    cycles = 0
    for _ in range(REVET_INTERVAL_CYCLES - 1):
        approved, cycles = maybe_revet(None, cycles, approved, vet_fn=fake_vet_fn)

    assert calls == []
    assert cycles == REVET_INTERVAL_CYCLES - 1
    assert approved == [("ETHUSDT", ALL_STRATEGIES[1], 0.4, 1.2)]


def test_maybe_revet_triggers_at_interval():
    calls = []

    def fake_vet_fn(conn):
        calls.append(conn)
        return ([("BTCUSDT", ALL_STRATEGIES[0], 0.5, 1.5)], {})

    approved = [("ETHUSDT", ALL_STRATEGIES[1], 0.4, 1.2)]
    cycles = REVET_INTERVAL_CYCLES - 1

    approved, cycles = maybe_revet("fake_conn", cycles, approved, vet_fn=fake_vet_fn)

    assert calls == ["fake_conn"]
    assert cycles == 0
    assert approved == [("BTCUSDT", ALL_STRATEGIES[0], 0.5, 1.5)]


def test_maybe_revet_survives_price_fetch_error():
    def failing_vet_fn(conn):
        raise PriceFetchError("non-200 response from Binance")

    approved = [("ETHUSDT", ALL_STRATEGIES[1], 0.4, 1.2)]
    cycles = REVET_INTERVAL_CYCLES - 1

    approved, cycles = maybe_revet("fake_conn", cycles, approved, vet_fn=failing_vet_fn)

    assert cycles == 0
    assert approved == [("ETHUSDT", ALL_STRATEGIES[1], 0.4, 1.2)]


def test_maybe_revet_survives_network_error():
    def failing_vet_fn(conn):
        raise requests.exceptions.ConnectionError("connection refused")

    approved = [("ETHUSDT", ALL_STRATEGIES[1], 0.4, 1.2)]
    cycles = REVET_INTERVAL_CYCLES - 1

    approved, cycles = maybe_revet("fake_conn", cycles, approved, vet_fn=failing_vet_fn)

    assert cycles == 0
    assert approved == [("ETHUSDT", ALL_STRATEGIES[1], 0.4, 1.2)]


def test_demoted_with_open_positions_includes_non_approved_symbol_with_open_trade(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    insert_trade(
        conn, symbol="SOLUSDT", side="buy", qty=1.0, price=100.0, fee=0.1,
        slippage=0.05, strategy="momentum", opened_at="2026-07-06T00:00:00",
    )
    approved = [("BTCUSDT", ALL_STRATEGIES[0], 0.5, 1.5)]  # momentum:SOLUSDT not approved

    demoted = _demoted_with_open_positions(conn, approved)

    assert len(demoted) == 1
    symbol, strategy, win_rate, payoff_ratio = demoted[0]
    assert symbol == "SOLUSDT"
    assert strategy.name == "momentum"
    assert win_rate == 0.0
    assert payoff_ratio == 0.0


def test_demoted_with_open_positions_excludes_approved_combo(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    momentum = next(s for s in ALL_STRATEGIES if s.name == "momentum")
    insert_trade(
        conn, symbol="SOLUSDT", side="buy", qty=1.0, price=100.0, fee=0.1,
        slippage=0.05, strategy="momentum", opened_at="2026-07-06T00:00:00",
    )
    approved = [("SOLUSDT", momentum, 0.5, 1.5)]  # momentum:SOLUSDT IS approved

    demoted = _demoted_with_open_positions(conn, approved)

    assert demoted == []


def test_demoted_with_open_positions_empty_when_no_open_trades(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    demoted = _demoted_with_open_positions(conn, [])
    assert demoted == []
