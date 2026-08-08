import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS margin_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    entry_price REAL NOT NULL,
    leverage INTEGER NOT NULL,
    margin REAL NOT NULL,
    liquidation_price REAL NOT NULL,
    funding_paid REAL NOT NULL DEFAULT 0,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    close_price REAL,
    pnl REAL,
    liquidated INTEGER NOT NULL DEFAULT 0
);
"""


def init_margin_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert_position(conn, *, symbol, side, qty, entry_price, leverage,
                     margin, liquidation_price, opened_at) -> int:
    cur = conn.execute(
        """INSERT INTO margin_positions
           (symbol, side, qty, entry_price, leverage, margin, liquidation_price, opened_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (symbol, side, qty, entry_price, leverage, margin, liquidation_price, opened_at),
    )
    conn.commit()
    return cur.lastrowid


def add_funding(conn, position_id: int, amount: float):
    conn.execute(
        "UPDATE margin_positions SET funding_paid = funding_paid + ? WHERE id = ?",
        (amount, position_id),
    )
    conn.commit()


def close_position(conn, position_id: int, *, close_price, pnl, closed_at, liquidated=False):
    conn.execute(
        """UPDATE margin_positions
           SET close_price = ?, pnl = ?, closed_at = ?, liquidated = ?
           WHERE id = ?""",
        (close_price, pnl, closed_at, int(liquidated), position_id),
    )
    conn.commit()


def get_open_positions(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM margin_positions WHERE closed_at IS NULL").fetchall()
    return [dict(row) for row in rows]


def get_all_positions(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM margin_positions ORDER BY id").fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["liquidated"] = bool(d["liquidated"])
        result.append(d)
    return result
