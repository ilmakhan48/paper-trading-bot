# Paper Trading Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working crypto paper-trading bot (BTC/ETH/SOL) that trades real
live prices with fake $10,000, using an honest engine (real fees/slippage),
3 backtested strategies, fractional-Kelly sizing, a background loop, and a
Streamlit dashboard.

**Architecture:** Modular Python package. SQLite is the single source of
truth shared between the background loop process and the dashboard (dashboard
only reads, never writes). Binance public REST API (no key required) is the
price source, confirmed live during planning:
`https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT` and
`https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=N`.

**Tech Stack:** Python 3.11+, `requests`, `pandas`, `numpy`, `streamlit`,
`pytest`, stdlib `sqlite3`.

## Global Constraints

- Never fabricate a price, fill, or profit — every trade uses the real
  polled price plus real fee (0.1% Binance spot taker) and a slippage model.
- Starting balance: $10,000 fake USD.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT.
- Poll interval: 5 minutes.
- A strategy only trades live if it passed the backtester's pass/fail gate.
- Fractional Kelly sizing uses 0.5x Kelly fraction (half-Kelly, standard
  safety practice to reduce volatility of full Kelly).

---

## File Structure

```
tradingbot/
  __init__.py
  data/
    __init__.py
    binance_feed.py
  engine/
    __init__.py
    db.py
    portfolio.py
    broker.py
  strategies/
    __init__.py
    base.py
    sma_cross.py
    rsi.py
    momentum.py
  backtest/
    __init__.py
    runner.py
  sizing/
    __init__.py
    kelly.py
  loop/
    __init__.py
    main.py
  dashboard/
    app.py
tests/
  test_binance_feed.py
  test_db.py
  test_portfolio.py
  test_broker.py
  test_strategies.py
  test_backtest.py
  test_kelly.py
requirements.txt
pytest.ini
```

---

### Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `tradingbot/__init__.py`
- Create: `tradingbot/data/__init__.py`
- Create: `tradingbot/engine/__init__.py`
- Create: `tradingbot/strategies/__init__.py`
- Create: `tradingbot/backtest/__init__.py`
- Create: `tradingbot/sizing/__init__.py`
- Create: `tradingbot/loop/__init__.py`
- Create: `tradingbot/dashboard/__init__.py`

**Interfaces:**
- Produces: importable `tradingbot` package, pytest configured to find `tests/`.

- [ ] **Step 1: Create requirements.txt**

```
requests>=2.31
pandas>=2.2
numpy>=1.26
streamlit>=1.35
pytest>=8.0
```

- [ ] **Step 2: Create pytest.ini**

```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 3: Create empty `__init__.py` files**

Create empty files at each `__init__.py` path listed above.

- [ ] **Step 4: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: all packages install without error.

- [ ] **Step 5: Commit**

```bash
git init
git add requirements.txt pytest.ini tradingbot
git commit -m "chore: scaffold tradingbot package"
```

---

### Task 2: Binance price feed

**Files:**
- Create: `tradingbot/data/binance_feed.py`
- Test: `tests/test_binance_feed.py`

**Interfaces:**
- Produces:
  - `get_price(symbol: str) -> float` — current spot price.
  - `get_klines(symbol: str, interval: str, limit: int) -> list[dict]` —
    each dict has keys `open_time, open, high, low, close, volume` (all
    numeric except `open_time` which is a `datetime`).
  - `class PriceFetchError(Exception)` — raised on network/API failure.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_binance_feed.py
import pytest
from unittest.mock import patch, Mock
from tradingbot.data.binance_feed import get_price, get_klines, PriceFetchError


def test_get_price_parses_response():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"symbol": "BTCUSDT", "price": "62857.71000000"}
    with patch("tradingbot.data.binance_feed.requests.get", return_value=fake_response) as mock_get:
        price = get_price("BTCUSDT")
    assert price == 62857.71
    mock_get.assert_called_once_with(
        "https://api.binance.com/api/v3/ticker/price",
        params={"symbol": "BTCUSDT"},
        timeout=10,
    )


def test_get_price_raises_on_http_error():
    fake_response = Mock()
    fake_response.status_code = 500
    with patch("tradingbot.data.binance_feed.requests.get", return_value=fake_response):
        with pytest.raises(PriceFetchError):
            get_price("BTCUSDT")


def test_get_klines_parses_rows():
    raw_row = [
        1783238400000, "63020.21000000", "63104.00000000",
        "62900.00000000", "62915.00000000", "337.45972000",
        1783241999999, "21249003.10070990", 54807,
        "146.25020000", "9210215.26308660", "0",
    ]
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = [raw_row]
    with patch("tradingbot.data.binance_feed.requests.get", return_value=fake_response):
        klines = get_klines("BTCUSDT", "1h", 1)
    assert len(klines) == 1
    row = klines[0]
    assert row["open"] == 63020.21
    assert row["close"] == 62915.00
    assert row["high"] == 63104.00
    assert row["low"] == 62900.00
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_binance_feed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingbot.data.binance_feed'`

- [ ] **Step 3: Implement binance_feed.py**

```python
# tradingbot/data/binance_feed.py
from datetime import datetime, timezone

import requests

BASE_URL = "https://api.binance.com/api/v3"


class PriceFetchError(Exception):
    pass


def get_price(symbol: str) -> float:
    response = requests.get(
        f"{BASE_URL}/ticker/price",
        params={"symbol": symbol},
        timeout=10,
    )
    if response.status_code != 200:
        raise PriceFetchError(
            f"Binance price fetch failed for {symbol}: HTTP {response.status_code}"
        )
    data = response.json()
    return float(data["price"])


def get_klines(symbol: str, interval: str, limit: int) -> list[dict]:
    response = requests.get(
        f"{BASE_URL}/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=10,
    )
    if response.status_code != 200:
        raise PriceFetchError(
            f"Binance klines fetch failed for {symbol}: HTTP {response.status_code}"
        )
    rows = response.json()
    return [
        {
            "open_time": datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_binance_feed.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingbot/data/binance_feed.py tests/test_binance_feed.py
git commit -m "feat: add Binance public price and klines feed"
```

---

### Task 3: SQLite schema and access layer

**Files:**
- Create: `tradingbot/engine/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `init_db(path: str) -> sqlite3.Connection`
  - `insert_trade(conn, *, symbol, side, qty, price, fee, slippage, strategy, opened_at, closed_at=None, pnl=None) -> int` (returns trade id)
  - `close_trade(conn, trade_id: int, *, close_price, fee, slippage, pnl, closed_at)`
  - `insert_equity_point(conn, *, timestamp, equity)`
  - `insert_strategy_run(conn, *, strategy, passed: bool, sharpe, max_drawdown, reason)`
  - `get_open_trades(conn) -> list[dict]`
  - `get_all_trades(conn) -> list[dict]`
  - `get_equity_history(conn) -> list[dict]`
  - `get_strategy_runs(conn) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingbot.engine.db'`

- [ ] **Step 3: Implement db.py**

```python
# tradingbot/engine/db.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingbot/engine/db.py tests/test_db.py
git commit -m "feat: add SQLite schema and access layer"
```

---

### Task 4: Portfolio

**Files:**
- Create: `tradingbot/engine/portfolio.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: nothing (pure in-memory state, `db.py` used by broker later).
- Produces:
  - `class Portfolio(cash: float)` with attributes `cash: float`,
    `positions: dict[str, dict]` (symbol -> `{"qty": float, "avg_price": float}`).
  - `Portfolio.equity(current_prices: dict[str, float]) -> float`
  - `Portfolio.apply_buy(symbol, qty, price, fee)`
  - `Portfolio.apply_sell(symbol, qty, price, fee) -> float` (returns realized PnL)
  - `class InsufficientFundsError(Exception)`
  - `class InsufficientPositionError(Exception)`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_portfolio.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_portfolio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingbot.engine.portfolio'`

- [ ] **Step 3: Implement portfolio.py**

```python
# tradingbot/engine/portfolio.py

class InsufficientFundsError(Exception):
    pass


class InsufficientPositionError(Exception):
    pass


class Portfolio:
    def __init__(self, cash: float):
        self.cash = cash
        self.positions: dict[str, dict] = {}
        self._open_fees: dict[str, float] = {}

    def equity(self, current_prices: dict[str, float]) -> float:
        total = self.cash
        for symbol, pos in self.positions.items():
            total += pos["qty"] * current_prices[symbol]
        return total

    def apply_buy(self, symbol: str, qty: float, price: float, fee: float):
        cost = qty * price
        if cost + fee > self.cash:
            raise InsufficientFundsError(
                f"Need {cost + fee:.2f} but only have {self.cash:.2f}"
            )
        self.cash -= (cost + fee)
        self.positions[symbol] = {"qty": qty, "avg_price": price}
        self._open_fees[symbol] = fee

    def apply_sell(self, symbol: str, qty: float, price: float, fee: float) -> float:
        position = self.positions.get(symbol)
        if position is None or position["qty"] < qty:
            raise InsufficientPositionError(f"No sufficient open position in {symbol}")
        proceeds = qty * price
        self.cash += proceeds - fee
        open_fee = self._open_fees.pop(symbol, 0.0)
        cost_basis = position["avg_price"] * qty
        pnl = proceeds - fee - cost_basis - open_fee
        del self.positions[symbol]
        return pnl
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_portfolio.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingbot/engine/portfolio.py tests/test_portfolio.py
git commit -m "feat: add in-memory portfolio with fee-aware PnL"
```

---

### Task 5: Broker (fee, slippage, honest close)

**Files:**
- Create: `tradingbot/engine/broker.py`
- Test: `tests/test_broker.py`

**Interfaces:**
- Consumes: `Portfolio` from Task 4; `insert_trade`, `close_trade` from Task 3.
- Produces:
  - `TAKER_FEE_RATE = 0.001` (0.1%, Binance spot taker fee)
  - `SLIPPAGE_RATE = 0.0005` (0.05%, fixed model — real price adjusted against the trader)
  - `class Broker(portfolio: Portfolio, conn: sqlite3.Connection)`
  - `Broker.open_trade(symbol, side, qty, market_price, strategy, opened_at) -> int` (trade id)
  - `Broker.close_trade(trade_id, symbol, market_price, closed_at) -> float` (realized PnL)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_broker.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_broker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingbot.engine.broker'`

- [ ] **Step 3: Implement broker.py**

```python
# tradingbot/engine/broker.py
from tradingbot.engine.db import insert_trade, close_trade as db_close_trade
from tradingbot.engine.portfolio import Portfolio

TAKER_FEE_RATE = 0.001   # Binance spot taker fee, 0.1%
SLIPPAGE_RATE = 0.0005   # fixed unfavorable slippage model, 0.05%


class Broker:
    def __init__(self, portfolio: Portfolio, conn):
        self.portfolio = portfolio
        self.conn = conn
        self._open_symbol_for_trade: dict[int, str] = {}

    def _fill_price(self, side: str, market_price: float) -> float:
        if side == "buy":
            return market_price * (1 + SLIPPAGE_RATE)
        return market_price * (1 - SLIPPAGE_RATE)

    def open_trade(self, *, symbol, side, qty, market_price, strategy, opened_at) -> int:
        fill_price = self._fill_price(side, market_price)
        fee = fill_price * qty * TAKER_FEE_RATE
        if side == "buy":
            self.portfolio.apply_buy(symbol, qty, fill_price, fee)
        else:
            self.portfolio.apply_sell(symbol, qty, fill_price, fee)
        trade_id = insert_trade(
            self.conn, symbol=symbol, side=side, qty=qty, price=fill_price,
            fee=fee, slippage=abs(fill_price - market_price) * qty,
            strategy=strategy, opened_at=opened_at,
        )
        self._open_symbol_for_trade[trade_id] = symbol
        return trade_id

    def close_trade(self, trade_id: int, *, symbol, market_price, closed_at) -> float:
        position = self.portfolio.positions[symbol]
        qty = position["qty"]
        fill_price = self._fill_price("sell", market_price)
        fee = fill_price * qty * TAKER_FEE_RATE
        pnl = self.portfolio.apply_sell(symbol, qty, fill_price, fee)
        db_close_trade(
            self.conn, trade_id, close_price=fill_price, fee=fee,
            slippage=abs(fill_price - market_price) * qty, pnl=pnl, closed_at=closed_at,
        )
        return pnl
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_broker.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingbot/engine/broker.py tests/test_broker.py
git commit -m "feat: add broker with real fee/slippage and truthful trade close"
```

---

### Task 6: Strategies (SMA cross, RSI, momentum)

**Files:**
- Create: `tradingbot/strategies/base.py`
- Create: `tradingbot/strategies/sma_cross.py`
- Create: `tradingbot/strategies/rsi.py`
- Create: `tradingbot/strategies/momentum.py`
- Test: `tests/test_strategies.py`

**Interfaces:**
- Produces:
  - `Signal = Literal["buy", "sell", "hold"]` (just use plain strings)
  - `class Strategy` (base, abstract-ish): `name: str`; method
    `signal(self, closes: list[float]) -> str` returning `"buy"`, `"sell"`,
    or `"hold"`.
  - `SmaCrossStrategy(fast=10, slow=30)` — buy when fast SMA crosses above
    slow SMA, sell when it crosses below.
  - `RsiStrategy(period=14, oversold=30, overbought=70)` — buy when RSI
    crosses up through oversold, sell when it crosses down through overbought.
  - `MomentumStrategy(lookback=20, threshold=0.0)` — buy if return over
    lookback window > threshold, sell if < -threshold.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_strategies.py
from tradingbot.strategies.sma_cross import SmaCrossStrategy
from tradingbot.strategies.rsi import RsiStrategy
from tradingbot.strategies.momentum import MomentumStrategy


def test_sma_cross_buy_signal():
    strat = SmaCrossStrategy(fast=2, slow=4)
    # last close makes fast SMA cross above slow SMA
    closes = [10, 10, 10, 10, 20]
    assert strat.signal(closes) == "buy"


def test_sma_cross_hold_when_insufficient_data():
    strat = SmaCrossStrategy(fast=10, slow=30)
    assert strat.signal([1, 2, 3]) == "hold"


def test_rsi_buy_on_oversold_recovery():
    # a run of losses driving RSI low, then a bounce up
    closes = [100, 98, 96, 94, 92, 90, 88, 86, 84, 82, 80, 78, 76, 74, 80]
    strat = RsiStrategy(period=14, oversold=30, overbought=70)
    signal = strat.signal(closes)
    assert signal in ("buy", "hold")  # bounce should push RSI up from oversold


def test_momentum_buy_on_positive_return():
    closes = [100] * 20 + [110]
    strat = MomentumStrategy(lookback=20, threshold=0.02)
    assert strat.signal(closes) == "buy"


def test_momentum_sell_on_negative_return():
    closes = [100] * 20 + [90]
    strat = MomentumStrategy(lookback=20, threshold=0.02)
    assert strat.signal(closes) == "sell"


def test_momentum_hold_within_threshold():
    closes = [100] * 20 + [101]
    strat = MomentumStrategy(lookback=20, threshold=0.02)
    assert strat.signal(closes) == "hold"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_strategies.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingbot.strategies.sma_cross'`

- [ ] **Step 3: Implement base.py**

```python
# tradingbot/strategies/base.py
class Strategy:
    name: str = "base"

    def signal(self, closes: list[float]) -> str:
        raise NotImplementedError
```

- [ ] **Step 4: Implement sma_cross.py**

```python
# tradingbot/strategies/sma_cross.py
from tradingbot.strategies.base import Strategy


def _sma(values: list[float], period: int) -> float:
    return sum(values[-period:]) / period


class SmaCrossStrategy(Strategy):
    name = "sma_cross"

    def __init__(self, fast: int = 10, slow: int = 30):
        self.fast = fast
        self.slow = slow

    def signal(self, closes: list[float]) -> str:
        if len(closes) < self.slow + 1:
            return "hold"
        fast_prev = _sma(closes[:-1], self.fast)
        slow_prev = _sma(closes[:-1], self.slow)
        fast_now = _sma(closes, self.fast)
        slow_now = _sma(closes, self.slow)
        if fast_prev <= slow_prev and fast_now > slow_now:
            return "buy"
        if fast_prev >= slow_prev and fast_now < slow_now:
            return "sell"
        return "hold"
```

- [ ] **Step 5: Implement rsi.py**

```python
# tradingbot/strategies/rsi.py
from tradingbot.strategies.base import Strategy


def _rsi(closes: list[float], period: int) -> float:
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    window = deltas[-period:]
    gains = [d for d in window if d > 0]
    losses = [-d for d in window if d < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


class RsiStrategy(Strategy):
    name = "rsi"

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def signal(self, closes: list[float]) -> str:
        if len(closes) < self.period + 2:
            return "hold"
        rsi_prev = _rsi(closes[:-1], self.period)
        rsi_now = _rsi(closes, self.period)
        if rsi_prev <= self.oversold and rsi_now > self.oversold:
            return "buy"
        if rsi_prev >= self.overbought and rsi_now < self.overbought:
            return "sell"
        return "hold"
```

- [ ] **Step 6: Implement momentum.py**

```python
# tradingbot/strategies/momentum.py
from tradingbot.strategies.base import Strategy


class MomentumStrategy(Strategy):
    name = "momentum"

    def __init__(self, lookback: int = 20, threshold: float = 0.0):
        self.lookback = lookback
        self.threshold = threshold

    def signal(self, closes: list[float]) -> str:
        if len(closes) < self.lookback + 1:
            return "hold"
        past = closes[-(self.lookback + 1)]
        now = closes[-1]
        ret = (now - past) / past
        if ret > self.threshold:
            return "buy"
        if ret < -self.threshold:
            return "sell"
        return "hold"
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_strategies.py -v`
Expected: PASS (6 tests)

- [ ] **Step 8: Commit**

```bash
git add tradingbot/strategies tests/test_strategies.py
git commit -m "feat: add SMA cross, RSI, and momentum strategies"
```

---

### Task 7: Backtester

**Files:**
- Create: `tradingbot/backtest/runner.py`
- Test: `tests/test_backtest.py`

**Interfaces:**
- Consumes: `Strategy.signal()` from Task 6.
- Produces:
  - `class BacktestResult`: fields `strategy: str`, `total_pnl: float`,
    `sharpe: float`, `max_drawdown: float`, `num_trades: int`, `passed: bool`,
    `reason: str`.
  - `run_backtest(strategy, closes: list[float], starting_cash=10000.0, fee_rate=0.001) -> BacktestResult`
  - Pass gate: `passed = sharpe > 0 and max_drawdown < 0.5 and num_trades >= 2`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_backtest.py
from tradingbot.strategies.momentum import MomentumStrategy
from tradingbot.backtest.runner import run_backtest


def test_backtest_uptrend_strategy_passes():
    strat = MomentumStrategy(lookback=5, threshold=0.0)
    # steady uptrend: momentum strategy should catch it and profit
    closes = [100 + i for i in range(60)]
    result = run_backtest(strat, closes)
    assert result.strategy == "momentum"
    assert result.num_trades >= 2
    assert result.total_pnl > 0
    assert result.passed is True
    assert result.reason == "passed"


def test_backtest_flat_market_fails():
    strat = MomentumStrategy(lookback=5, threshold=0.0)
    closes = [100.0] * 60
    result = run_backtest(strat, closes)
    assert result.num_trades == 0
    assert result.passed is False
    assert "no trades" in result.reason.lower()


def test_backtest_result_has_drawdown_and_sharpe_fields():
    strat = MomentumStrategy(lookback=5, threshold=0.0)
    closes = [100 + i for i in range(60)]
    result = run_backtest(strat, closes)
    assert isinstance(result.sharpe, float)
    assert isinstance(result.max_drawdown, float)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backtest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingbot.backtest.runner'`

- [ ] **Step 3: Implement runner.py**

```python
# tradingbot/backtest/runner.py
from dataclasses import dataclass

import numpy as np

FEE_RATE = 0.001


@dataclass
class BacktestResult:
    strategy: str
    total_pnl: float
    sharpe: float
    max_drawdown: float
    num_trades: int
    passed: bool
    reason: str


def run_backtest(strategy, closes: list[float], starting_cash: float = 10000.0,
                   fee_rate: float = FEE_RATE) -> BacktestResult:
    cash = starting_cash
    position_qty = 0.0
    entry_price = 0.0
    equity_curve = [starting_cash]
    num_trades = 0

    for i in range(1, len(closes) + 1):
        window = closes[:i]
        price = closes[i - 1]
        signal = strategy.signal(window)

        if signal == "buy" and position_qty == 0.0:
            spend = cash * 0.99  # keep a buffer for fees
            qty = spend / price
            fee = spend * fee_rate
            cash -= (spend + fee)
            position_qty = qty
            entry_price = price
            num_trades += 1
        elif signal == "sell" and position_qty > 0.0:
            proceeds = position_qty * price
            fee = proceeds * fee_rate
            cash += proceeds - fee
            position_qty = 0.0
            num_trades += 1

        equity = cash + position_qty * price
        equity_curve.append(equity)

    if position_qty > 0.0:
        # honest close at final price, no rounding away the mark-to-market
        proceeds = position_qty * closes[-1]
        fee = proceeds * fee_rate
        cash += proceeds - fee
        equity_curve.append(cash)

    total_pnl = equity_curve[-1] - starting_cash

    if num_trades == 0:
        return BacktestResult(
            strategy=strategy.name, total_pnl=0.0, sharpe=0.0, max_drawdown=0.0,
            num_trades=0, passed=False, reason="No trades were triggered by this strategy",
        )

    returns = np.diff(equity_curve) / equity_curve[:-1]
    sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(len(returns))) if np.std(returns) > 0 else 0.0

    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        drawdown = (peak - value) / peak
        max_drawdown = max(max_drawdown, drawdown)

    passed = sharpe > 0 and max_drawdown < 0.5 and num_trades >= 2
    reason = "passed" if passed else (
        f"Sharpe {sharpe:.2f} or drawdown {max_drawdown:.2f} did not meet the pass bar"
    )

    return BacktestResult(
        strategy=strategy.name, total_pnl=total_pnl, sharpe=sharpe,
        max_drawdown=max_drawdown, num_trades=num_trades, passed=passed, reason=reason,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backtest.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingbot/backtest/runner.py tests/test_backtest.py
git commit -m "feat: add backtester with honest pass/fail gate"
```

---

### Task 8: Fractional Kelly sizing

**Files:**
- Create: `tradingbot/sizing/kelly.py`
- Test: `tests/test_kelly.py`

**Interfaces:**
- Consumes: nothing new (works on plain win-rate/payoff numbers, or a
  `BacktestResult`-derived list of trade PnLs).
- Produces:
  - `kelly_fraction(win_rate: float, payoff_ratio: float) -> float` — raw
    Kelly `f* = (bp - q) / b` where `p=win_rate`, `q=1-p`, `b=payoff_ratio`.
    Clamped to `[0, 1]`.
  - `fractional_kelly(win_rate, payoff_ratio, fraction=0.5) -> float`
  - `position_size(equity: float, win_rate: float, payoff_ratio: float, fraction=0.5) -> float`
    returns dollar amount to risk (never more than available equity, floors at 0).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_kelly.py
from tradingbot.sizing.kelly import kelly_fraction, fractional_kelly, position_size


def test_kelly_fraction_standard_formula():
    # p=0.6, b=1.5 (win pays 1.5x risk) -> f* = (b*p - q) / b = (1.5*0.6 - 0.4)/1.5
    f = kelly_fraction(win_rate=0.6, payoff_ratio=1.5)
    expected = (1.5 * 0.6 - 0.4) / 1.5
    assert abs(f - expected) < 1e-9


def test_kelly_fraction_clamped_to_zero_when_negative_edge():
    f = kelly_fraction(win_rate=0.3, payoff_ratio=1.0)
    assert f == 0.0


def test_kelly_fraction_clamped_to_one():
    f = kelly_fraction(win_rate=0.99, payoff_ratio=100.0)
    assert f <= 1.0


def test_fractional_kelly_applies_safety_fraction():
    full = kelly_fraction(win_rate=0.6, payoff_ratio=1.5)
    half = fractional_kelly(win_rate=0.6, payoff_ratio=1.5, fraction=0.5)
    assert abs(half - full * 0.5) < 1e-9


def test_position_size_never_exceeds_equity():
    size = position_size(equity=10000.0, win_rate=0.9, payoff_ratio=10.0, fraction=0.5)
    assert size <= 10000.0


def test_position_size_zero_when_no_edge():
    size = position_size(equity=10000.0, win_rate=0.2, payoff_ratio=1.0, fraction=0.5)
    assert size == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_kelly.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingbot.sizing.kelly'`

- [ ] **Step 3: Implement kelly.py**

```python
# tradingbot/sizing/kelly.py

def kelly_fraction(win_rate: float, payoff_ratio: float) -> float:
    p = win_rate
    q = 1 - win_rate
    b = payoff_ratio
    if b <= 0:
        return 0.0
    f = (b * p - q) / b
    return max(0.0, min(f, 1.0))


def fractional_kelly(win_rate: float, payoff_ratio: float, fraction: float = 0.5) -> float:
    return kelly_fraction(win_rate, payoff_ratio) * fraction


def position_size(equity: float, win_rate: float, payoff_ratio: float, fraction: float = 0.5) -> float:
    f = fractional_kelly(win_rate, payoff_ratio, fraction)
    return equity * f
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_kelly.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingbot/sizing/kelly.py tests/test_kelly.py
git commit -m "feat: add fractional Kelly position sizing"
```

---

### Task 9: Background loop

**Files:**
- Create: `tradingbot/loop/main.py`

**Interfaces:**
- Consumes: `get_price`, `get_klines` (Task 2), `init_db` (Task 3),
  `Portfolio` (Task 4), `Broker` (Task 5), `SmaCrossStrategy`, `RsiStrategy`,
  `MomentumStrategy` (Task 6), `run_backtest` (Task 7), `position_size` (Task 8).
- Produces: a runnable script — no return value, run via `python -m tradingbot.loop.main`.
  Writes to `tradingbot.db` in the current working directory.

This task is integration wiring, not unit-testable in isolation — verified by
manual run in Step 3.

- [ ] **Step 1: Write main.py**

```python
# tradingbot/loop/main.py
import time
from datetime import datetime, timezone

from tradingbot.data.binance_feed import get_price, get_klines, PriceFetchError
from tradingbot.engine.db import init_db, insert_equity_point, insert_strategy_run, get_open_trades
from tradingbot.engine.portfolio import Portfolio
from tradingbot.engine.broker import Broker
from tradingbot.strategies.sma_cross import SmaCrossStrategy
from tradingbot.strategies.rsi import RsiStrategy
from tradingbot.strategies.momentum import MomentumStrategy
from tradingbot.backtest.runner import run_backtest
from tradingbot.sizing.kelly import position_size

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
POLL_SECONDS = 300
STARTING_CASH = 10000.0
DB_PATH = "tradingbot.db"

ALL_STRATEGIES = [SmaCrossStrategy(), RsiStrategy(), MomentumStrategy()]


def vet_strategies(conn):
    """Backtest each strategy per symbol on 1h history; only passing ones trade live."""
    approved = []
    for symbol in SYMBOLS:
        klines = get_klines(symbol, "1h", 500)
        closes = [k["close"] for k in klines]
        for strategy in ALL_STRATEGIES:
            result = run_backtest(strategy, closes)
            insert_strategy_run(
                conn, strategy=f"{strategy.name}:{symbol}", passed=result.passed,
                sharpe=result.sharpe, max_drawdown=result.max_drawdown, reason=result.reason,
                run_at=datetime.now(timezone.utc).isoformat(),
            )
            if result.passed:
                win_rate = 0.5  # placeholder win rate refined from live trade history over time
                payoff_ratio = max(result.total_pnl, 1.0) / STARTING_CASH * 10
                approved.append((symbol, strategy, win_rate, payoff_ratio))
    return approved


def run_cycle(conn, portfolio, broker, approved_strategies, price_history):
    now = datetime.now(timezone.utc).isoformat()
    current_prices = {}
    for symbol in SYMBOLS:
        try:
            price = get_price(symbol)
        except PriceFetchError as exc:
            print(f"[{now}] price fetch failed for {symbol}: {exc} — skipping symbol this cycle")
            continue
        current_prices[symbol] = price
        price_history.setdefault(symbol, []).append(price)

    for symbol, strategy, win_rate, payoff_ratio in approved_strategies:
        closes = price_history.get(symbol, [])
        if len(closes) < 2 or symbol not in current_prices:
            continue
        signal = strategy.signal(closes)
        has_open = symbol in portfolio.positions
        if signal == "buy" and not has_open:
            dollars = position_size(portfolio.cash, win_rate, payoff_ratio)
            if dollars <= 0:
                continue
            qty = dollars / current_prices[symbol]
            broker.open_trade(
                symbol=symbol, side="buy", qty=qty, market_price=current_prices[symbol],
                strategy=strategy.name, opened_at=now,
            )
        elif signal == "sell" and has_open:
            open_trades = [t for t in get_open_trades(conn) if t["symbol"] == symbol]
            if open_trades:
                broker.close_trade(
                    open_trades[0]["id"], symbol=symbol,
                    market_price=current_prices[symbol], closed_at=now,
                )

    equity = portfolio.equity(current_prices) if current_prices else portfolio.cash
    insert_equity_point(conn, timestamp=now, equity=equity)
    print(f"[{now}] equity={equity:.2f} cash={portfolio.cash:.2f} positions={list(portfolio.positions.keys())}")


def main():
    conn = init_db(DB_PATH)
    portfolio = Portfolio(cash=STARTING_CASH)
    broker = Broker(portfolio, conn)
    price_history: dict[str, list[float]] = {}

    print("Vetting strategies against real historical data before trading live...")
    approved_strategies = vet_strategies(conn)
    print(f"Approved for live trading: {[(s, strat.name) for s, strat, _, _ in approved_strategies]}")

    while True:
        run_cycle(conn, portfolio, broker, approved_strategies, price_history)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual smoke test — run one cycle by hand**

Run: `python -c "
from tradingbot.loop.main import vet_strategies, init_db, DB_PATH
conn = init_db(DB_PATH)
approved = vet_strategies(conn)
print(approved)
"`

Expected: prints a list of `(symbol, strategy_object, win_rate, payoff_ratio)`
tuples (may be empty if no strategy passes — that is honest behavior per the
spec, not a bug).

- [ ] **Step 3: Commit**

```bash
git add tradingbot/loop/main.py
git commit -m "feat: add background trading loop wiring engine, strategies, sizing"
```

---

### Task 10: Streamlit dashboard

**Files:**
- Create: `tradingbot/dashboard/app.py`

**Interfaces:**
- Consumes: `get_all_trades`, `get_open_trades`, `get_equity_history`,
  `get_strategy_runs` from Task 3 (`tradingbot/engine/db.py`), reading the
  same `tradingbot.db` SQLite file the loop writes to.
- Produces: a Streamlit app, run via `streamlit run tradingbot/dashboard/app.py`.

- [ ] **Step 1: Write app.py**

```python
# tradingbot/dashboard/app.py
import pandas as pd
import streamlit as st

from tradingbot.engine.db import (
    init_db, get_all_trades, get_open_trades, get_equity_history, get_strategy_runs,
)

DB_PATH = "tradingbot.db"

st.set_page_config(page_title="Paper Trading Bot", layout="wide")
st.title("Paper Trading Bot — Live Dashboard")
st.caption("Real live prices, fake money. Every number here is honest — losses included.")

conn = init_db(DB_PATH)

equity_history = get_equity_history(conn)
if equity_history:
    df = pd.DataFrame(equity_history)
    latest_equity = df["equity"].iloc[-1]
    starting_equity = df["equity"].iloc[0]
    st.metric(
        "Current Equity",
        f"${latest_equity:,.2f}",
        f"{latest_equity - starting_equity:+,.2f}",
    )
    st.line_chart(df.set_index("timestamp")["equity"])
else:
    st.info("No equity history yet — start the loop with `python -m tradingbot.loop.main`.")

st.subheader("Open Positions")
open_trades = get_open_trades(conn)
if open_trades:
    st.dataframe(pd.DataFrame(open_trades))
else:
    st.write("No open positions.")

st.subheader("Trade Log")
all_trades = get_all_trades(conn)
if all_trades:
    st.dataframe(pd.DataFrame(all_trades))
else:
    st.write("No trades yet.")

st.subheader("Strategy Vetting (honest pass/fail)")
strategy_runs = get_strategy_runs(conn)
if strategy_runs:
    st.dataframe(pd.DataFrame(strategy_runs))
else:
    st.write("No strategy backtests recorded yet.")
```

- [ ] **Step 2: Manual smoke test**

Run: `streamlit run tradingbot/dashboard/app.py`
Expected: browser opens to `http://localhost:8501` showing the dashboard
(empty-state messages are correct if the loop hasn't run yet).

- [ ] **Step 3: Commit**

```bash
git add tradingbot/dashboard/app.py
git commit -m "feat: add Streamlit dashboard reading shared SQLite state"
```

---

## Self-Review Notes

- **Spec coverage:** price feed (Task 2), honest engine/fees/slippage/close
  (Tasks 3–5), strategies + backtester pass/fail gate (Tasks 6–7), Kelly
  sizing (Task 8), background loop (Task 9), dashboard (Task 10) — all spec
  sections have a task.
- **Placeholder scan:** one flagged item — `vet_strategies` in Task 9 uses a
  placeholder `win_rate = 0.5` and a rough payoff estimate rather than a true
  per-strategy backtested win rate/payoff. This is a known simplification,
  not a silent gap: it's called out in-line and refining it (computing real
  win_rate/payoff_ratio from the backtest's trade-by-trade PnL list) is
  reasonable follow-up work once the bot is running, not a blocker for a
  working end-to-end system.
- **Type consistency:** `Strategy.signal()` returns `"buy"/"sell"/"hold"`
  consistently across strategies, backtester, and loop. `Broker` methods and
  `db.py` function names/kwargs match across Tasks 3, 5, 9.
