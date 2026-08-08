import pytest
from tradingbot.margin.db import (
    init_margin_db, insert_position, add_funding, close_position,
    get_open_positions, get_all_positions,
)


def test_insert_and_get_open_position(tmp_path):
    conn = init_margin_db(str(tmp_path / "m.db"))
    position_id = insert_position(
        conn, symbol="BTCUSDT", side="long", qty=0.01, entry_price=60000.0,
        leverage=10, margin=60.0, liquidation_price=54240.0,
        opened_at="2026-07-05T00:00:00",
    )
    open_positions = get_open_positions(conn)
    assert len(open_positions) == 1
    assert open_positions[0]["id"] == position_id
    assert open_positions[0]["liquidated"] == 0
    assert open_positions[0]["closed_at"] is None


def test_add_funding_accumulates(tmp_path):
    conn = init_margin_db(str(tmp_path / "m.db"))
    position_id = insert_position(
        conn, symbol="BTCUSDT", side="long", qty=0.01, entry_price=60000.0,
        leverage=10, margin=60.0, liquidation_price=54240.0,
        opened_at="2026-07-05T00:00:00",
    )
    add_funding(conn, position_id, -0.5)
    add_funding(conn, position_id, -0.3)
    positions = get_open_positions(conn)
    assert positions[0]["funding_paid"] == pytest.approx(-0.8)


def test_close_position_marks_closed_with_liquidated_flag(tmp_path):
    conn = init_margin_db(str(tmp_path / "m.db"))
    position_id = insert_position(
        conn, symbol="BTCUSDT", side="long", qty=0.01, entry_price=60000.0,
        leverage=10, margin=60.0, liquidation_price=54240.0,
        opened_at="2026-07-05T00:00:00",
    )
    close_position(
        conn, position_id, close_price=54240.0, pnl=-60.0,
        closed_at="2026-07-05T00:05:00", liquidated=True,
    )
    assert get_open_positions(conn) == []
    all_positions = get_all_positions(conn)
    assert all_positions[0]["liquidated"] is True
    assert all_positions[0]["pnl"] == pytest.approx(-60.0)
