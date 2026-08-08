# Periodic Strategy Re-vetting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing spot paper-trading bot re-check each strategy
against fresh price history every 6 hours (72 cycles), demoting strategies
that stop passing and promoting ones that start passing, instead of trusting
the one-time startup vetting forever.

**Architecture:** Two small additions to `tradingbot/loop/main.py`: a pure
`maybe_revet()` helper that decides when to re-run the existing
`vet_strategies()` and swaps in the new approved list, and a
`_demoted_with_open_positions()` helper that lets a just-demoted
strategy still evaluate its signal for symbols where it already holds an
open position (so it can close honestly) without being allowed to open new
ones.

**Tech Stack:** Python, `pytest`, stdlib `sqlite3` (via the existing
`tradingbot.engine.db` module).

## Global Constraints

- Re-vet every 72 cycles (6 hours at the existing 300-second poll
  interval) — not a shorter or longer default.
- A demoted strategy (present in the *previous* approved list, absent from
  the *new* one) must still be evaluated for signals on any symbol where it
  currently holds an open position, so it can close on its own exit
  signal — but must never open a new position until it passes vetting
  again.
- No changes to `tradingbot/engine/`, `tradingbot/strategies/`,
  `tradingbot/backtest/`, `tradingbot/sizing/`, `tradingbot/margin/`, or the
  dashboard.
- `price_history` (the live-polled series) is untouched by re-vetting —
  re-vetting only replaces `approved_strategies`, using its own fresh
  klines fetch exactly like the original startup vetting.

---

## File Structure

```
tradingbot/loop/main.py   # modified: add maybe_revet(), _demoted_with_open_positions(),
                          # wire both into main()'s loop and run_cycle()
tests/test_loop_revetting.py   # new: unit tests for both helpers
```

---

### Task 1: Re-vetting helpers and wiring

**Files:**
- Modify: `tradingbot/loop/main.py`
- Test: `tests/test_loop_revetting.py`

**Interfaces:**
- Consumes: `vet_strategies(conn)` (existing, returns `(approved, history_seed)`),
  `get_open_trades(conn)` (existing, from `tradingbot.engine.db`),
  `ALL_STRATEGIES` (existing module-level list of strategy instances),
  `run_cycle(conn, portfolio, broker, approved_strategies, price_history)`
  (existing — this task changes its internal behavior, not its signature).
- Produces:
  - `REVET_INTERVAL_CYCLES = 72` (module constant)
  - `maybe_revet(conn, cycles_since_vet: int, approved_strategies: list, vet_fn=vet_strategies, revet_interval: int = REVET_INTERVAL_CYCLES) -> tuple[list, int]` —
    returns `(approved_strategies, cycles_since_vet)` unchanged if the
    interval hasn't elapsed; otherwise calls `vet_fn(conn)`, returns
    `(new_approved_strategies, 0)`.
  - `_demoted_with_open_positions(conn, approved_strategies: list) -> list` —
    returns a list of `(symbol, strategy, 0.0, 0.0)` tuples (same 4-tuple
    shape as `approved_strategies`, with win_rate/payoff zeroed since
    they're never used to size a new trade) for every open trade in the DB
    whose `(symbol, strategy_name)` pair is NOT in `approved_strategies`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_loop_revetting.py
import pytest
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_loop_revetting.py -v`
Expected: FAIL — `ImportError: cannot import name 'maybe_revet' from 'tradingbot.loop.main'`

- [ ] **Step 3: Implement the helpers in tradingbot/loop/main.py**

Add the constant near the other module constants (after `POLL_SECONDS`):

```python
REVET_INTERVAL_CYCLES = 72  # 6 hours at the 300-second poll interval
```

Add these two functions after `vet_strategies` and before `run_cycle`:

```python
def maybe_revet(conn, cycles_since_vet, approved_strategies,
                 vet_fn=vet_strategies, revet_interval=REVET_INTERVAL_CYCLES):
    """Re-run vet_fn every `revet_interval` cycles; otherwise pass through unchanged.

    Returns (approved_strategies, cycles_since_vet) for the caller to carry
    into the next cycle.
    """
    cycles_since_vet += 1
    if cycles_since_vet < revet_interval:
        return approved_strategies, cycles_since_vet
    new_approved, _ = vet_fn(conn)
    return new_approved, 0


def _demoted_with_open_positions(conn, approved_strategies):
    """Strategy/symbol pairs with an open trade whose strategy isn't currently approved.

    Returned so a just-demoted strategy can still evaluate its signal to
    close an existing position honestly, without being allowed to open a
    new one (callers must gate opening on membership in
    `approved_strategies`, not this list).
    """
    approved_keys = {(symbol, strategy.name) for symbol, strategy, _, _ in approved_strategies}
    strategies_by_name = {s.name: s for s in ALL_STRATEGIES}
    seen = set()
    result = []
    for trade in get_open_trades(conn):
        key = (trade["symbol"], trade["strategy"])
        if key in approved_keys or key in seen:
            continue
        strategy = strategies_by_name.get(trade["strategy"])
        if strategy is None:
            continue
        seen.add(key)
        result.append((trade["symbol"], strategy, 0.0, 0.0))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_loop_revetting.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Wire the helpers into run_cycle and main()**

Replace `run_cycle`'s existing trading loop body (the `for symbol, strategy,
win_rate, payoff_ratio in approved_strategies:` loop and everything inside
it) with:

```python
def run_cycle(conn, portfolio, broker, approved_strategies, price_history):
    now = datetime.now(timezone.utc).isoformat()
    current_prices = {}
    for symbol in SYMBOLS:
        try:
            price = get_price(symbol)
        except (PriceFetchError, requests.exceptions.RequestException) as exc:
            print(f"[{now}] price fetch failed for {symbol}: {exc} — skipping symbol this cycle")
            continue
        current_prices[symbol] = price
        price_history.setdefault(symbol, []).append(price)

    approved_keys = {(symbol, strategy.name) for symbol, strategy, _, _ in approved_strategies}
    evaluate_set = [
        (symbol, strategy, win_rate, payoff_ratio, True)
        for symbol, strategy, win_rate, payoff_ratio in approved_strategies
    ] + [
        (symbol, strategy, win_rate, payoff_ratio, False)
        for symbol, strategy, win_rate, payoff_ratio in _demoted_with_open_positions(conn, approved_strategies)
    ]

    for symbol, strategy, win_rate, payoff_ratio, can_open in evaluate_set:
        closes = price_history.get(symbol, [])
        if len(closes) < 2 or symbol not in current_prices:
            continue
        signal = strategy.signal(closes)
        has_open = symbol in portfolio.positions
        if signal == "buy" and not has_open and can_open:
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
```

Then update `main()`'s loop to call `maybe_revet` each iteration:

```python
def main():
    conn = init_db(DB_PATH)
    portfolio = Portfolio(cash=STARTING_CASH)
    broker = Broker(portfolio, conn)

    print("Vetting strategies against real historical data before trading live...")
    approved_strategies, price_history = vet_strategies(conn)
    print(f"Approved for live trading: {[(s, strat.name) for s, strat, _, _ in approved_strategies]}")
    cycles_since_vet = 0

    while True:
        try:
            run_cycle(conn, portfolio, broker, approved_strategies, price_history)
        except Exception as exc:  # noqa: BLE001 - one bad cycle must never kill the loop
            now = datetime.now(timezone.utc).isoformat()
            print(f"[{now}] run_cycle failed unexpectedly: {exc!r} — continuing to next cycle")
        approved_strategies, cycles_since_vet = maybe_revet(conn, cycles_since_vet, approved_strategies)
        time.sleep(POLL_SECONDS)
```

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: all tests pass, including the 5 new ones and every pre-existing
test (spot engine, margin engine) — this task only modifies
`tradingbot/loop/main.py`, which has no existing unit tests of its own
(it was previously verified only by manual smoke test), so no existing
test file should need updating.

- [ ] **Step 7: Commit**

```bash
git add tradingbot/loop/main.py tests/test_loop_revetting.py
git commit -m "feat: add periodic strategy re-vetting to the background loop"
```

---

### Task 2: Manual smoke test with a shortened interval

**Files:** none created — this task only runs and verifies the Task 1
code against real data, mirroring how the original loop (Task 9 in the
first plan) and the margin engine (Task 5 in its plan) were verified.

**Interfaces:**
- Consumes: `maybe_revet`, `vet_strategies`, `run_cycle`, `main` internals
  from Task 1.

- [ ] **Step 1: Run a real end-to-end check with a patched-down interval**

Run this from the repo root (adjust the venv activation to whatever this
machine uses):

```bash
python -c "
from tradingbot.engine.db import init_db
from tradingbot.engine.portfolio import Portfolio
from tradingbot.engine.broker import Broker
from tradingbot.loop.main import vet_strategies, maybe_revet, run_cycle, STARTING_CASH

conn = init_db(':memory:')
portfolio = Portfolio(cash=STARTING_CASH)
broker = Broker(portfolio, conn)

print('Vetting against real Binance history...')
approved_strategies, price_history = vet_strategies(conn)
print('Initially approved:', [(s, strat.name) for s, strat, _, _ in approved_strategies])

cycles_since_vet = 0
for i in range(5):
    run_cycle(conn, portfolio, broker, approved_strategies, price_history)
    # patch revet_interval down to 3 so this real 5-iteration run actually re-vets once
    approved_strategies, cycles_since_vet = maybe_revet(
        conn, cycles_since_vet, approved_strategies, revet_interval=3,
    )
    print(f'cycle {i+1}: cycles_since_vet={cycles_since_vet}, approved={[(s, strat.name) for s, strat, _, _ in approved_strategies]}')
"
```

Expected: prints real vetting results using live Binance data, runs 5 real
cycles without crashing, and shows `cycles_since_vet` reset to `0` (with a
fresh `approved` printout, possibly the same combos, possibly different —
either is fine since it's real market data) after the 3rd cycle.

- [ ] **Step 2: Run the full test suite one more time**

Run: `pytest -v`
Expected: all tests still pass (no regressions from the smoke test, since
it doesn't touch any file, just exercises the running code).

- [ ] **Step 3: Report**

No commit for this task — just confirm in your report that the smoke test
output looked real (actual symbol/strategy names, actual sharpe-driven
pass/fail, not placeholder text) and the full suite is green.

---

## Self-Review Notes

- **Spec coverage:** re-vet interval + trigger (Task 1's `maybe_revet`),
  promotion/demotion via approved-list replacement (Task 1), demoted-can-
  still-close behavior (Task 1's `_demoted_with_open_positions` +
  `run_cycle` wiring), fresh `strategy_runs` rows on each re-vet (already
  handled by the existing `vet_strategies`, unchanged, called again by
  `maybe_revet`), real-data verification (Task 2) — all spec sections
  covered. Dashboard needs no change since it already reads
  `strategy_runs` in full.
- **Placeholder scan:** none — Task 1 Step 5 includes an explicit note
  flagging one line to leave out of the final code (a drafting leftover),
  which is a real, actionable instruction, not a TBD.
- **Type consistency:** `approved_strategies` stays a list of 4-tuples
  `(symbol, strategy, win_rate, payoff_ratio)` everywhere — `vet_strategies`,
  `maybe_revet`, `_demoted_with_open_positions`, and `run_cycle`'s
  `evaluate_set` construction (which adds a 5th `can_open` element locally,
  never fed back into `approved_strategies` itself) are all consistent.
