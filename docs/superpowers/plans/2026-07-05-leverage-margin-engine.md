# Leverage/Margin Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, isolated-margin leverage engine (long and short,
up to 20x) with real funding rate and liquidation price, as a new
`tradingbot/margin/` package that doesn't touch the existing spot engine.

**Architecture:** Four small modules mirroring the existing spot engine's
pattern (`tradingbot/engine/`): a real-data funding/mark-price feed, a
SQLite table + CRUD layer, an in-memory portfolio with the margin math, and
a broker that wires portfolio + DB together and handles forced liquidation.

**Tech Stack:** Python, `requests`, stdlib `sqlite3`, `pytest`.

## Global Constraints

- Isolated margin only (each position's own margin; no cross-margin).
- Long and short positions, leverage 1-20x.
- Real funding rate and mark price from Binance's public futures API
  (no key needed), confirmed live during planning:
  `https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT` (mark price)
  `https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1` (funding rate)
- Never fake a price, fill, funding rate, or liquidation — a fetch failure
  skips that check, never substitutes a stale/fabricated number.
- Maintenance margin rate (MMR) for the liquidation formula: **0.4%**
  (Binance's well-established tier-1 rate for BTCUSDT/ETHUSDT/SOLUSDT, for
  position notional under $50,000 — this project's paper positions are far
  below that). This number could not be scraped from Binance's JS-rendered
  margin tier page during planning; **the implementer of Task 3 must
  re-verify it against Binance's official leverage/margin documentation
  (`https://www.binance.com/en/futures/trading-rules/perpetual/leverage-margin`)
  before finalizing, and note in their report whether it's still current.**
  If it has changed, use the real current value instead of 0.4% and say so.
- Funding sign convention (confirmed during planning): when the funding
  rate is positive, longs pay shorts; when negative, shorts pay longs.
- This plan builds the engine only, verified standalone — it is not wired
  into the background loop or dashboard (that's a later sub-project).

---

## File Structure

```
tradingbot/margin/
  __init__.py
  funding.py    # get_mark_price(symbol), get_funding_rate(symbol)
  db.py         # margin_positions table + CRUD
  portfolio.py  # liquidation_price(), MarginPosition, MarginPortfolio
  broker.py     # MarginBroker: wires portfolio + db, handles liquidation
tests/
  test_funding.py
  test_margin_db.py
  test_margin_portfolio.py
  test_margin_broker.py
```

---

### Task 1: Funding/mark-price feed

**Files:**
- Create: `tradingbot/margin/__init__.py` (empty)
- Create: `tradingbot/margin/funding.py`
- Test: `tests/test_funding.py`

**Interfaces:**
- Produces:
  - `get_mark_price(symbol: str) -> float`
  - `get_funding_rate(symbol: str) -> float`
  - `class FundingFetchError(Exception)`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_funding.py
import pytest
from unittest.mock import patch, Mock
from tradingbot.margin.funding import get_mark_price, get_funding_rate, FundingFetchError


def test_get_mark_price_parses_response():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "symbol": "BTCUSDT", "markPrice": "62700.30000000",
        "indexPrice": "62728.07456522", "lastFundingRate": "0.00010000",
        "nextFundingTime": 1783267200000, "time": 1783254516000,
    }
    with patch("tradingbot.margin.funding.requests.get", return_value=fake_response) as mock_get:
        price = get_mark_price("BTCUSDT")
    assert price == 62700.30
    mock_get.assert_called_once_with(
        "https://fapi.binance.com/fapi/v1/premiumIndex",
        params={"symbol": "BTCUSDT"},
        timeout=10,
    )


def test_get_mark_price_raises_on_http_error():
    fake_response = Mock()
    fake_response.status_code = 500
    with patch("tradingbot.margin.funding.requests.get", return_value=fake_response):
        with pytest.raises(FundingFetchError):
            get_mark_price("BTCUSDT")


def test_get_funding_rate_parses_most_recent():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = [
        {"symbol": "BTCUSDT", "fundingTime": 1783238400001,
         "fundingRate": "0.00008873", "markPrice": "62997.87521014"}
    ]
    with patch("tradingbot.margin.funding.requests.get", return_value=fake_response) as mock_get:
        rate = get_funding_rate("BTCUSDT")
    assert rate == pytest.approx(0.00008873)
    mock_get.assert_called_once_with(
        "https://fapi.binance.com/fapi/v1/fundingRate",
        params={"symbol": "BTCUSDT", "limit": 1},
        timeout=10,
    )


def test_get_funding_rate_raises_on_http_error():
    fake_response = Mock()
    fake_response.status_code = 500
    with patch("tradingbot.margin.funding.requests.get", return_value=fake_response):
        with pytest.raises(FundingFetchError):
            get_funding_rate("BTCUSDT")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_funding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingbot.margin.funding'`

- [ ] **Step 3: Implement funding.py**

```python
# tradingbot/margin/funding.py
import requests

BASE_URL = "https://fapi.binance.com/fapi/v1"


class FundingFetchError(Exception):
    pass


def get_mark_price(symbol: str) -> float:
    response = requests.get(
        f"{BASE_URL}/premiumIndex",
        params={"symbol": symbol},
        timeout=10,
    )
    if response.status_code != 200:
        raise FundingFetchError(
            f"Binance mark price fetch failed for {symbol}: HTTP {response.status_code}"
        )
    data = response.json()
    return float(data["markPrice"])


def get_funding_rate(symbol: str) -> float:
    response = requests.get(
        f"{BASE_URL}/fundingRate",
        params={"symbol": symbol, "limit": 1},
        timeout=10,
    )
    if response.status_code != 200:
        raise FundingFetchError(
            f"Binance funding rate fetch failed for {symbol}: HTTP {response.status_code}"
        )
    rows = response.json()
    return float(rows[0]["fundingRate"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_funding.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingbot/margin/__init__.py tradingbot/margin/funding.py tests/test_funding.py
git commit -m "feat: add Binance futures mark price and funding rate feed"
```

---

### Task 2: Margin positions DB table + CRUD

**Files:**
- Create: `tradingbot/margin/db.py`
- Test: `tests/test_margin_db.py`

**Interfaces:**
- Produces:
  - `init_margin_db(path: str) -> sqlite3.Connection`
  - `insert_position(conn, *, symbol, side, qty, entry_price, leverage, margin, liquidation_price, opened_at) -> int` (returns id)
  - `add_funding(conn, position_id: int, amount: float)`
  - `close_position(conn, position_id: int, *, close_price, pnl, closed_at, liquidated=False)`
  - `get_open_positions(conn) -> list[dict]`
  - `get_all_positions(conn) -> list[dict]` (each dict's `liquidated` is a real `bool`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_margin_db.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_margin_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingbot.margin.db'`

- [ ] **Step 3: Implement db.py**

```python
# tradingbot/margin/db.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_margin_db.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingbot/margin/db.py tests/test_margin_db.py
git commit -m "feat: add margin_positions SQLite table and CRUD layer"
```

---

### Task 3: MarginPortfolio and liquidation math

**Files:**
- Create: `tradingbot/margin/portfolio.py`
- Test: `tests/test_margin_portfolio.py`

**Interfaces:**
- Consumes: nothing (pure in-memory state).
- Produces:
  - `MAINTENANCE_MARGIN_RATE = 0.004` (re-verify per Global Constraints before trusting)
  - `liquidation_price(entry_price: float, leverage: int, side: str, mmr: float = MAINTENANCE_MARGIN_RATE) -> float`
  - `class MarginPosition` (dataclass): `symbol, side, qty, entry_price, leverage, margin, liquidation_price, funding_paid=0.0`
  - `class MarginPortfolio(cash: float)` with `cash: float`, `positions: dict[str, MarginPosition]`
  - `MarginPortfolio.open_position(symbol, side, qty, entry_price, leverage) -> MarginPosition`
  - `MarginPortfolio.apply_funding(symbol, funding_rate, mark_price) -> float` (returns the cash change applied)
  - `MarginPortfolio.close_position(symbol, close_price) -> float` (returns realized PnL)
  - `class InsufficientMarginError(Exception)`
  - `class PositionAlreadyClosedError(Exception)`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_margin_portfolio.py
import pytest
from tradingbot.margin.portfolio import (
    MarginPortfolio, liquidation_price, InsufficientMarginError,
    PositionAlreadyClosedError, MAINTENANCE_MARGIN_RATE,
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_margin_portfolio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingbot.margin.portfolio'`

- [ ] **Step 3: Before implementing — verify MAINTENANCE_MARGIN_RATE**

Check `https://www.binance.com/en/futures/trading-rules/perpetual/leverage-margin`
(or another official Binance source) for BTCUSDT's current tier-1
maintenance margin rate. If you can confirm a current value, use it. If the
page cannot be scraped/verified in your environment either, keep `0.004`
(0.4%) as a clearly-labeled, disclosed assumption and say so in your
report — do not silently invent a different number.

- [ ] **Step 4: Implement portfolio.py**

```python
# tradingbot/margin/portfolio.py
from dataclasses import dataclass

MAINTENANCE_MARGIN_RATE = 0.004  # Binance tier-1 MMR, BTCUSDT/ETHUSDT/SOLUSDT under $50,000 notional -- re-verify per plan's Global Constraints


class InsufficientMarginError(Exception):
    pass


class PositionAlreadyClosedError(Exception):
    pass


def liquidation_price(entry_price: float, leverage: int, side: str,
                       mmr: float = MAINTENANCE_MARGIN_RATE) -> float:
    if side == "long":
        return entry_price * (1 - 1 / leverage + mmr)
    elif side == "short":
        return entry_price * (1 + 1 / leverage - mmr)
    else:
        raise ValueError(f"side must be 'long' or 'short', got {side!r}")


@dataclass
class MarginPosition:
    symbol: str
    side: str
    qty: float
    entry_price: float
    leverage: int
    margin: float
    liquidation_price: float
    funding_paid: float = 0.0


class MarginPortfolio:
    def __init__(self, cash: float):
        self.cash = cash
        self.positions: dict[str, MarginPosition] = {}

    def open_position(self, symbol: str, side: str, qty: float,
                       entry_price: float, leverage: int) -> MarginPosition:
        notional = qty * entry_price
        margin = notional / leverage
        if margin > self.cash:
            raise InsufficientMarginError(
                f"Need {margin:.2f} margin but only have {self.cash:.2f}"
            )
        liq_price = liquidation_price(entry_price, leverage, side)
        position = MarginPosition(
            symbol=symbol, side=side, qty=qty, entry_price=entry_price,
            leverage=leverage, margin=margin, liquidation_price=liq_price,
        )
        self.cash -= margin
        self.positions[symbol] = position
        return position

    def apply_funding(self, symbol: str, funding_rate: float, mark_price: float) -> float:
        position = self.positions[symbol]
        notional = position.qty * mark_price
        if position.side == "long":
            payment = -notional * funding_rate
        else:
            payment = notional * funding_rate
        self.cash += payment
        position.funding_paid += payment
        return payment

    def close_position(self, symbol: str, close_price: float) -> float:
        position = self.positions.get(symbol)
        if position is None:
            raise PositionAlreadyClosedError(f"No open position for {symbol}")
        if position.side == "long":
            pnl = position.qty * (close_price - position.entry_price)
        else:
            pnl = position.qty * (position.entry_price - close_price)
        self.cash += position.margin + pnl
        del self.positions[symbol]
        return pnl
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_margin_portfolio.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add tradingbot/margin/portfolio.py tests/test_margin_portfolio.py
git commit -m "feat: add MarginPortfolio with liquidation price and funding math"
```

---

### Task 4: MarginBroker (wires portfolio + DB, handles forced liquidation)

**Files:**
- Create: `tradingbot/margin/broker.py`
- Test: `tests/test_margin_broker.py`

**Interfaces:**
- Consumes: `MarginPortfolio`, `MarginPosition` (Task 3); `insert_position`,
  `add_funding`, `close_position` from `tradingbot/margin/db.py` (Task 2).
- Produces:
  - `class MarginBroker(portfolio: MarginPortfolio, conn)`
  - `MarginBroker.open_position(*, symbol, side, qty, entry_price, leverage, opened_at) -> int` (position id)
  - `MarginBroker.apply_funding(symbol, funding_rate, mark_price) -> float`
  - `MarginBroker.close_position(symbol, close_price, closed_at) -> float` (realized PnL)
  - `MarginBroker.check_liquidation(symbol, mark_price, closed_at) -> bool` (True if this call force-closed the position)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_margin_broker.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_margin_broker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingbot.margin.broker'`

- [ ] **Step 3: Implement broker.py**

```python
# tradingbot/margin/broker.py
from tradingbot.margin.db import insert_position, add_funding, close_position as db_close_position
from tradingbot.margin.portfolio import MarginPortfolio


class MarginBroker:
    def __init__(self, portfolio: MarginPortfolio, conn):
        self.portfolio = portfolio
        self.conn = conn
        self._position_ids: dict[str, int] = {}

    def open_position(self, *, symbol, side, qty, entry_price, leverage, opened_at) -> int:
        position = self.portfolio.open_position(symbol, side, qty, entry_price, leverage)
        position_id = insert_position(
            self.conn, symbol=symbol, side=side, qty=qty, entry_price=entry_price,
            leverage=leverage, margin=position.margin,
            liquidation_price=position.liquidation_price, opened_at=opened_at,
        )
        self._position_ids[symbol] = position_id
        return position_id

    def apply_funding(self, symbol, funding_rate, mark_price) -> float:
        payment = self.portfolio.apply_funding(symbol, funding_rate, mark_price)
        add_funding(self.conn, self._position_ids[symbol], payment)
        return payment

    def close_position(self, symbol, close_price, closed_at) -> float:
        pnl = self.portfolio.close_position(symbol, close_price)
        position_id = self._position_ids.pop(symbol)
        db_close_position(
            self.conn, position_id, close_price=close_price, pnl=pnl,
            closed_at=closed_at, liquidated=False,
        )
        return pnl

    def check_liquidation(self, symbol, mark_price, closed_at) -> bool:
        position = self.portfolio.positions.get(symbol)
        if position is None:
            return False
        breached = (
            (position.side == "long" and mark_price <= position.liquidation_price)
            or (position.side == "short" and mark_price >= position.liquidation_price)
        )
        if not breached:
            return False
        pnl = self.portfolio.close_position(symbol, position.liquidation_price)
        position_id = self._position_ids.pop(symbol)
        db_close_position(
            self.conn, position_id, close_price=position.liquidation_price, pnl=pnl,
            closed_at=closed_at, liquidated=True,
        )
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_margin_broker.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingbot/margin/broker.py tests/test_margin_broker.py
git commit -m "feat: add MarginBroker with real funding and forced liquidation"
```

---

### Task 5: Manual smoke test against real Binance futures data

**Files:** none created — this task only runs and verifies existing code
against live data. No loop/dashboard wiring (out of scope, deferred to the
episodes sub-project).

**Interfaces:**
- Consumes: everything from Tasks 1-4.

- [ ] **Step 1: Run a real end-to-end check**

Run this from the repo root (adjust the venv activation to whatever this
machine uses — see prior tasks' environment notes if `pip`/`venv` are
broken on Homebrew Python):

```bash
python -c "
from tradingbot.margin.funding import get_mark_price, get_funding_rate
from tradingbot.margin.db import init_margin_db, get_all_positions
from tradingbot.margin.portfolio import MarginPortfolio
from tradingbot.margin.broker import MarginBroker

mark_price = get_mark_price('BTCUSDT')
funding_rate = get_funding_rate('BTCUSDT')
print('real mark price:', mark_price)
print('real funding rate:', funding_rate)

conn = init_margin_db(':memory:')
portfolio = MarginPortfolio(cash=1000.0)
broker = MarginBroker(portfolio, conn)
position_id = broker.open_position(
    symbol='BTCUSDT', side='long', qty=0.001, entry_price=mark_price,
    leverage=10, opened_at='2026-07-05T00:00:00',
)
print('opened position', position_id, 'liq price:', portfolio.positions['BTCUSDT'].liquidation_price)

broker.apply_funding('BTCUSDT', funding_rate=funding_rate, mark_price=mark_price)
print('after funding, cash:', portfolio.cash)

liquidated = broker.check_liquidation('BTCUSDT', mark_price=mark_price, closed_at='2026-07-05T00:01:00')
print('liquidated at current price (should be False):', liquidated)

pnl = broker.close_position('BTCUSDT', close_price=mark_price, closed_at='2026-07-05T00:02:00')
print('closed, pnl:', pnl)
print('all positions:', get_all_positions(conn))
"
```

Expected: prints a real mark price and funding rate (not zero, not
obviously fake), opens/funds/checks/closes without raising, and the final
`all positions` list shows one closed, non-liquidated position with a
small PnL (close price ≈ entry price, so PnL should be near zero, not
exactly zero because of the tiny time gap between fetching mark_price and
using it — this is fine and expected).

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: all tests from this plan plus all pre-existing spot-engine tests
pass (this plan adds new modules, touches nothing existing).

- [ ] **Step 3: Report**

No commit for this task (nothing new to add to git) — just confirm in your
report that the manual smoke test output looked real and the full suite is
green.

---

## Self-Review Notes

- **Spec coverage:** funding/mark-price feed (Task 1), margin_positions
  table (Task 2), portfolio + liquidation math + funding math (Task 3),
  broker wiring + forced liquidation (Task 4), standalone real-data
  verification (Task 5) — all spec sections covered. Loop/dashboard wiring
  is explicitly out of scope per the spec, so no task attempts it.
- **Placeholder scan:** `MAINTENANCE_MARGIN_RATE = 0.4%` is a disclosed,
  documented assumption with an explicit re-verification step (Task 3, Step
  3) — not a silent placeholder. No other TBDs.
- **Type consistency:** `side` is `"long"`/`"short"` consistently across
  `liquidation_price()`, `MarginPosition`, `MarginPortfolio`, and
  `MarginBroker`. DB column names match the kwargs used in `insert_position`/
  `close_position` across Tasks 2 and 4.
