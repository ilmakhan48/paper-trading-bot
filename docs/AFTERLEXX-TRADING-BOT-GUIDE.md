[AFTERLEXX LOGO]

# Ilma Khanum Trading Bot — Built by AFTERLEXX

**Internal Engineering Documentation — v1.0**

---

## About This Bot

I built this. It's a paper-trading bot for crypto — BTC, ETH, and SOL — that trades against real, live market prices with simulated money, using rule-based strategies that have to prove themselves on real historical data before they're allowed anywhere near a live decision. No strategy goes live on a hunch. No fill, price, or profit in this system is ever fabricated — if the bot can't get a real number, it says so and skips the cycle instead of making one up.

I built it with Claude (Anthropic) as my AI engineering partner — not as a black-box "AI trading brain" bolted onto the front, but as the tool I used to design, implement, test, and review every module in this codebase, task by task, with real test evidence at every step. This document is that system, written down completely enough that anyone on the AFTERLEXX team could stand up an identical instance from scratch.

— Ilma Khanum, AFTERLEXX

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Core Build Principles](#3-core-build-principles)
4. [System Components](#4-system-components-labeled-by-function)
5. [Step-by-Step Operational Guide](#5-step-by-step-operational-guide)
6. [Setup & Configuration](#6-setup--configuration)
7. [Rebuilding From Scratch](#7-rebuilding-from-scratch)
8. [Disclaimer](#8-disclaimer)

---

## 1. Overview

**What it does:** Runs a continuous paper-trading loop against three cryptocurrencies, using real live prices, real (simulated) fees and slippage, and rule-based strategies that are only allowed to trade if they pass a real backtest first. Every few hours it re-checks its own strategies against fresh data and promotes or demotes them automatically — that's the "learns from its mistakes" behavior.

**What it does NOT do:** It does not execute real trades on a real exchange. It does not risk real money. There is no live order routing, no exchange API keys, no withdrawal capability anywhere in this codebase. It is a simulation, deliberately.

| | |
|---|---|
| **Assets traded** | BTC/USDT, ETH/USDT, SOL/USDT (Binance spot pairs) |
| **Mode** | Paper trading (simulated cash, real prices) |
| **Starting balance** | $10,000.00 (simulated) |
| **Data source** | Binance public REST API (spot market data, no API key required) |
| **Language / runtime** | Python 3.9 |
| **Persistence** | SQLite (single local `.db` file) |
| **Dashboard** | Streamlit + Altair |
| **Strategies** | SMA crossover, RSI threshold, Momentum (all rule-based, no ML/LLM inference at runtime) |
| **Position sizing** | Half-Kelly, derived from each strategy's real backtested win rate and payoff ratio |
| **Poll interval** | Every 300 seconds (5 minutes) |
| **Re-vet interval** | Every 72 cycles (~6 hours) |
| **AI's role** | Development partner (design, implementation, testing, code review) — not a runtime trading component |

---

## 2. Architecture

```
                        ┌─────────────────────────┐
                        │   Binance Public REST    │
                        │  api.binance.com/api/v3  │
                        │  (ticker/price, klines)  │
                        └────────────┬─────────────┘
                                     │  live price + candle data
                                     ▼
┌────────────────────────────────────────────────────────────────┐
│                      tradingbot/loop/main.py                    │
│                     (background process, runs forever)          │
│                                                                   │
│   ┌─────────────┐   ┌───────────────┐   ┌────────────────────┐ │
│   │  vet_strategies│─▶│ backtest.runner│──▶│  approved_strategies│ │
│   │  (every 72   │   │  run_backtest  │   │  (per symbol/strat) │ │
│   │   cycles)    │   │  (Sharpe/DD/   │   └──────────┬─────────┘ │
│   └─────────────┘   │  trade-count   │              │            │
│                      │  pass gate)    │              │            │
│                      └───────────────┘              ▼            │
│                                          ┌────────────────────┐  │
│   live price ──────────────────────────▶│ strategy.signal()  │  │
│   (per symbol, per cycle)                │ (SMA/RSI/Momentum) │  │
│                                          └──────────┬─────────┘  │
│                                                     │ buy/sell/hold│
│                                                     ▼             │
│                                     ┌───────────────────────────┐│
│                                     │ sizing.kelly.position_size ││
│                                     │ (half-Kelly, real win-rate ││
│                                     │  + payoff ratio)           ││
│                                     └──────────────┬────────────┘│
│                                                    ▼              │
│                                     ┌───────────────────────────┐│
│                                     │  engine.broker.Broker      ││
│                                     │  (applies fee + slippage,  ││
│                                     │   mutates Portfolio)       ││
│                                     └──────────────┬────────────┘│
└────────────────────────────────────────────────────┼─────────────┘
                                                       ▼
                                      ┌─────────────────────────────┐
                                      │      SQLite (tradingbot.db)  │
                                      │  trades / equity_history /   │
                                      │  strategy_runs               │
                                      └───────────────┬───────────────┘
                                                       ▼
                                      ┌─────────────────────────────┐
                                      │  tradingbot/dashboard/app.py │
                                      │  (Streamlit, reads DB +      │
                                      │   one live price call)       │
                                      └─────────────────────────────┘
```

Two independent OS processes share the same SQLite file: the background loop (writer) and the dashboard (reader + one live price call of its own for unrealized P&L).

---

## 3. Core Build Principles

These are the actual operating rules I held Claude to throughout development — the real instructions that shaped every module below, not example/illustrative prompts. Every commit in this codebase was built and reviewed against these.

```
RULE: Never fake a fill, a price, or a profit.
Applies to: every module that touches money or market data.
Meaning: if a real price/fill/fee can't be obtained, the system must say so
and skip that unit of work — never substitute a guessed, rounded, or
last-known-good value and present it as current.
```

```
RULE: Verify, don't guess.
Applies to: every constant, formula, and API assumption in the codebase.
Meaning: fee rates, endpoint behavior, and formulas were checked against
real API responses or official docs before being written into code. Where
a value genuinely couldn't be verified (see Section 4, Risk Layer), it's
explicitly disclosed as an assumption in the code comments, not presented
as fact.
```

```
RULE: A strategy only trades live if it earns it.
Applies to: tradingbot/backtest/runner.py + tradingbot/loop/main.py.
Meaning: no strategy is wired into the live loop directly. It must pass a
real backtest against real historical candles first (Section 4, Signal
Layer), and it's re-checked periodically — passing once is not permanent.
```

```
RULE: Every task ships with real test evidence.
Applies to: the entire development process.
Meaning: each module was built test-first, with actual pytest output
(pass/fail counts, not descriptions of expected behavior) attached to every
commit, plus an independent code review pass before being marked done.
```

---

## 4. System Components (labeled by function)

### 4.1 Market Data Layer — `tradingbot/data/binance_feed.py`

Fetches real live prices and historical candles from Binance's public spot API. No API key required — these are unauthenticated public endpoints.

```python
BASE_URL = "https://api.binance.com/api/v3"

def get_price(symbol: str) -> float:
    # GET {BASE_URL}/ticker/price?symbol={symbol}
    # Raises PriceFetchError on non-200 — never returns a stale/guessed price.

def get_klines(symbol: str, interval: str, limit: int) -> list[dict]:
    # GET {BASE_URL}/klines?symbol={symbol}&interval={interval}&limit={limit}
    # Returns list of {open_time, open, high, low, close, volume}.
```

**What it does:** Single source of truth for all price data in the system — both live polling and the historical candles used for backtesting come from this one module.

### 4.2 Signal Layer — `tradingbot/strategies/`

Three independent, deterministic, rule-based strategies. Each implements one method: `signal(closes: list[float]) -> "buy" | "sell" | "hold"`.

```python
# sma_cross.py — SMA Crossover
# fast=10, slow=30 period simple moving averages.
# buy: fast SMA crosses above slow SMA this bar (wasn't, now is).
# sell: fast SMA crosses below slow SMA this bar.
def signal(self, closes):
    fast_prev, slow_prev = _sma(closes[:-1], self.fast), _sma(closes[:-1], self.slow)
    fast_now, slow_now = _sma(closes, self.fast), _sma(closes, self.slow)
    if fast_prev <= slow_prev and fast_now > slow_now: return "buy"
    if fast_prev >= slow_prev and fast_now < slow_now: return "sell"
    return "hold"
```

```python
# rsi.py — RSI Threshold
# period=14, oversold=30, overbought=70.
# buy: RSI crosses up through the oversold line.
# sell: RSI crosses down through the overbought line.
def signal(self, closes):
    rsi_prev, rsi_now = _rsi(closes[:-1], self.period), _rsi(closes, self.period)
    if rsi_prev <= self.oversold and rsi_now > self.oversold: return "buy"
    if rsi_prev >= self.overbought and rsi_now < self.overbought: return "sell"
    return "hold"
```

```python
# momentum.py — Momentum
# lookback=20 bars, threshold=0.0.
# buy: return over the lookback window is positive.
# sell: return over the lookback window is negative.
def signal(self, closes):
    ret = (closes[-1] - closes[-(self.lookback + 1)]) / closes[-(self.lookback + 1)]
    if ret > self.threshold: return "buy"
    if ret < -self.threshold: return "sell"
    return "hold"
```

**What it does:** Produces the raw buy/sell/hold signal per symbol, per cycle. Nothing here decides position size or whether to actually act on the signal — that's the risk layer's job.

### 4.3 Risk Layer — `tradingbot/backtest/runner.py` + `tradingbot/sizing/kelly.py`

**Backtest gate** — runs a strategy against historical closes, simulating real fees, and only passes it if it earns the right to trade live:

```python
FEE_RATE = 0.001  # 0.1%, same as live taker fee

# Pass criteria — ALL three required:
passed = sharpe > 0 and max_drawdown < 0.5 and num_trades >= 2
```

**Position sizing** — half-Kelly, computed from the strategy's own real backtested trade outcomes (win rate and average win/loss ratio), never a fixed or guessed percentage:

```python
def kelly_fraction(win_rate, payoff_ratio):
    p, q, b = win_rate, 1 - win_rate, payoff_ratio
    if b <= 0: return 0.0
    return max(0.0, min((b * p - q) / b, 1.0))

def position_size(equity, win_rate, payoff_ratio, fraction=0.5):
    return equity * kelly_fraction(win_rate, payoff_ratio) * fraction
```

**What it does:** Gatekeeps which strategies are allowed to trade at all, and sizes every position based on that strategy's actual demonstrated edge — not a flat percentage of the account.

### 4.4 Execution Layer — `tradingbot/engine/broker.py` + `tradingbot/engine/portfolio.py`

Applies real, honest transaction costs to every simulated fill — this is what makes it "paper trading" and not a fantasy backtest running live.

```python
TAKER_FEE_RATE = 0.001   # Binance spot taker fee, 0.1% — matches real Binance fee schedule
SLIPPAGE_RATE = 0.0005   # fixed unfavorable slippage, 0.05% — applied against you, every trade

def _fill_price(side, market_price):
    # buy fills slightly above market; sell fills slightly below — always unfavorable
    return market_price * (1 + SLIPPAGE_RATE) if side == "buy" else market_price * (1 - SLIPPAGE_RATE)
```

`Portfolio` tracks cash and open positions and raises real errors (`InsufficientFundsError`, `InsufficientPositionError`) rather than silently allowing an impossible trade.

**What it does:** Converts an approved buy/sell decision into an actual state change — cash moves, a position opens or closes, fees and slippage are deducted, and the result is written to SQLite.

### 4.5 Re-vetting Layer — `tradingbot/loop/main.py`

The "learns from its mistakes" behavior. Every 72 cycles (~6 hours), every strategy is re-backtested against fresh 500-candle hourly history:

```python
REVET_INTERVAL_CYCLES = 72  # 6 hours at the 300-second poll interval

def maybe_revet(conn, cycles_since_vet, approved_strategies, vet_fn=vet_strategies, ...):
    cycles_since_vet += 1
    if cycles_since_vet < revet_interval:
        return approved_strategies, cycles_since_vet
    try:
        new_approved, _ = vet_fn(conn)
    except (PriceFetchError, requests.exceptions.RequestException) as exc:
        # keep current approvals, retry next interval — never crash the loop
        return approved_strategies, 0
    return new_approved, 0
```

A strategy that starts failing gets demoted (blocked from new positions, but still allowed to close any position it already holds honestly). A previously-rejected strategy that starts passing gets promoted.

**What it does:** Prevents the bot from trusting a stale, one-time vetting decision forever — the edge is re-earned on a schedule, automatically.

### 4.6 Dashboard — `tradingbot/dashboard/app.py`

Streamlit + Altair, reads directly from SQLite plus one live price call for unrealized P&L. Dark terminal theme, wallet breakdown (cash/invested/P&L), per-coin cards with 24h sparklines, color-coded open-position cards, gradient equity curve, trade log, and the strategy vetting history (honest pass/fail, not curated).

---

## 5. Step-by-Step Operational Guide

Full cycle, exactly as `tradingbot/loop/main.py` executes it every 300 seconds:

1. **Startup vetting** — on process start, call `vet_strategies()`: fetch 500 hourly candles per symbol from Binance, backtest all 3 strategies against each, log every result (pass or fail) to the `strategy_runs` table, and build the initial `approved_strategies` list from whichever combos passed.
2. **Seed price history** — reuse the same 500-candle series from step 1 as the starting `price_history` for live signal evaluation (keeps vetting and live trading on the same timeframe).
3. **Poll live prices** — for each of BTC/ETH/SOL, fetch the current price via `get_price()`. If a fetch fails, skip that symbol this cycle only — never substitute a stale price.
4. **Append to price history** — each successful price gets appended to that symbol's running `price_history` list, which grows over time as the loop runs.
5. **Build the evaluate-set** — the currently-approved strategy/symbol combos, plus any combo that isn't currently approved but still has an open position (so it can close honestly even after being demoted).
6. **Evaluate signals** — for each combo in the evaluate-set, call `strategy.signal(closes)` against that symbol's price history.
7. **Act on buy signals** — if signal is `"buy"`, no position is currently open, and the combo is currently approved: compute position size via half-Kelly (`position_size(cash, win_rate, payoff_ratio)`), convert to quantity at current price, call `broker.open_trade()`.
8. **Act on sell signals** — if signal is `"sell"` and a position is open: call `broker.close_trade()` regardless of current approval status (an open position always gets to close on its own signal).
9. **Log equity** — compute total portfolio equity (cash + mark-to-market open positions) and insert one row into `equity_history`.
10. **Re-vet check** — increment the cycle counter; if 72 cycles have elapsed since the last vetting pass, re-run step 1's vetting logic and replace `approved_strategies` with the fresh result (wrapped in error handling — a failed re-vet keeps the current approvals rather than crashing).
11. **Sleep** — wait 300 seconds, then repeat from step 3.

Any unexpected exception in a single cycle is caught at the top level and logged — it never kills the loop process.

---

## 6. Setup & Configuration

**API keys required: none.** Binance's spot `ticker/price` and `klines` endpoints used by this system are public and unauthenticated. There is nothing to rotate, secure, or leak here — no `.env` file, no secrets, by design.

**Environment variables:** none required. All configuration is in-code constants at the top of `tradingbot/loop/main.py`:

| Constant | Value | Meaning |
|---|---|---|
| `SYMBOLS` | `["BTCUSDT", "ETHUSDT", "SOLUSDT"]` | Traded pairs |
| `POLL_SECONDS` | `300` | Live poll interval |
| `REVET_INTERVAL_CYCLES` | `72` | Re-vetting interval (~6 hours) |
| `STARTING_CASH` | `10000.0` | Simulated starting balance |
| `DB_PATH` | `"tradingbot.db"` | SQLite file location |

**Dependencies** (`requirements.txt`):

```
requests>=2.31
pandas>=2.2
numpy>=1.26
streamlit>=1.35
pytest>=8.0
```

Note: `altair` is imported directly by the dashboard but is not pinned separately in `requirements.txt` — it installs transitively as a real dependency of `streamlit` itself. If you ever swap out Streamlit, pin `altair` explicitly.

**Runtime:** Python 3.9+. SQLite via the Python standard library — no separate database server to run.

**Running it:**

```bash
pip install -r requirements.txt

# Start the background trading loop
python -m tradingbot.loop.main

# In a second terminal, start the dashboard
streamlit run tradingbot/dashboard/app.py
```

---

## 7. Rebuilding From Scratch

To reproduce this exact system:

1. Set up the four core packages: `tradingbot/data/` (market data), `tradingbot/strategies/` (signal generation), `tradingbot/backtest/` (the pass/fail gate), `tradingbot/sizing/` (Kelly position sizing).
2. Build `tradingbot/engine/` (portfolio state, broker fill logic, SQLite schema/CRUD) on top of those — this is the only layer that mutates money state.
3. Wire it all together in `tradingbot/loop/main.py` following the 11-step cycle in Section 5 exactly — vet once at startup, then poll/evaluate/act/log/sleep, with periodic re-vetting layered on top.
4. Build `tradingbot/dashboard/app.py` as a read-only consumer of the same SQLite file, plus its own single live price call for unrealized P&L display.
5. At every step, hold to Section 3's four rules — especially "never fake a fill, a price, or a profit." That rule is what separates this from a toy backtest dressed up as a live system.

---

## 8. Disclaimer

This system is for internal AFTERLEXX use only. It trades with simulated money against real market data — it does not execute real trades, hold real funds, or connect to any exchange account. Nothing in this document or the underlying codebase constitutes financial advice. Trading cryptocurrency involves substantial risk of loss; past backtest performance does not predict future results. Do not represent this system's output as investment advice to any third party.

---

*Ilma Khanum Trading Bot — Built by AFTERLEXX*
