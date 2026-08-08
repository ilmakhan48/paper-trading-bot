import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    open_price REAL NOT NULL,
    close_price REAL,
    open_fee REAL NOT NULL,
    close_fee REAL,
    slippage REAL NOT NULL,
    strategy TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    pnl REAL
);

CREATE TABLE IF NOT EXISTS equity_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    equity REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    passed INTEGER NOT NULL,
    sharpe REAL,
    max_drawdown REAL,
    reason TEXT,
    run_at TEXT
);
"""


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert_trade(conn, *, symbol, side, qty, price, fee, slippage,
                  strategy, opened_at, closed_at=None, pnl=None) -> int:
    cur = conn.execute(
        """INSERT INTO trades
           (symbol, side, qty, open_price, open_fee, slippage, strategy, opened_at, closed_at, pnl)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (symbol, side, qty, price, fee, slippage, strategy, opened_at, closed_at, pnl),
    )
    conn.commit()
    return cur.lastrowid


def close_trade(conn, trade_id: int, *, close_price, fee, slippage, pnl, closed_at):
    conn.execute(
        """UPDATE trades SET close_price = ?, close_fee = ?, slippage = slippage + ?,
           pnl = ?, closed_at = ? WHERE id = ?""",
        (close_price, fee, slippage, pnl, closed_at, trade_id),
    )
    conn.commit()


def insert_equity_point(conn, *, timestamp, equity):
    conn.execute(
        "INSERT INTO equity_history (timestamp, equity) VALUES (?, ?)",
        (timestamp, equity),
    )
    conn.commit()


def insert_strategy_run(conn, *, strategy, passed, sharpe, max_drawdown, reason, run_at=None):
    conn.execute(
        """INSERT INTO strategy_runs (strategy, passed, sharpe, max_drawdown, reason, run_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (strategy, int(passed), sharpe, max_drawdown, reason, run_at),
    )
    conn.commit()


def get_open_trades(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM trades WHERE closed_at IS NULL").fetchall()
    return [dict(row) for row in rows]


def get_all_trades(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM trades ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def get_equity_history(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM equity_history ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def get_strategy_runs(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM strategy_runs ORDER BY id").fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["passed"] = bool(d["passed"])
        result.append(d)
    return result
