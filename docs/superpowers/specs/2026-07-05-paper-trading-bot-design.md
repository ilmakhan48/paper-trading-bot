# Paper Trading Bot — Design Spec

Date: 2026-07-05

## Purpose

Build a crypto paper-trading bot: trades real, live BTC/ETH/SOL prices with fake
money. No trading background assumed, no broker account needed. Core rule:
**never fake a fill, a price, or a profit.** If a strategy has no edge, the bot
must say so, not hide it.

## Scope

- Live price feed (Binance public REST API, crypto only, no API key)
- Honest trading engine: real fees, slippage, truthful losing-trade closes
- 3 simple strategies (SMA cross, RSI, momentum) + backtester that only keeps
  strategies that honestly pass on historical data
- Fractional Kelly position sizing
- Background loop process that runs continuously, polling every 5 minutes
- Streamlit dashboard for live viewing (equity curve, open positions, trade log)
- Starting balance: $10,000 fake USD

## Out of scope (for this spec)

- Real broker integration / real money execution
- Stocks or other asset classes
- Multi-user / auth
- Cloud deployment (runs locally only)

## Architecture

```
tradingbot/
  data/
    binance_feed.py    # polls Binance public REST for BTC/ETH/SOL spot price
  engine/
    portfolio.py       # cash balance, open positions, equity curve
    broker.py          # opens/closes trades; applies real taker fee (0.1%),
                        # slippage model, truthful loss on close
    db.py              # SQLite schema: trades, positions, equity_history,
                        # strategy_runs
  strategies/
    base.py            # Signal interface: given price history -> buy/sell/hold
    sma_cross.py
    rsi.py
    momentum.py
  backtest/
    runner.py           # replays historical candles through a strategy,
                         # computes PnL/Sharpe/max-drawdown, pass/fail gate
  sizing/
    kelly.py            # fractional Kelly sizer from strategy's historical
                         # win rate + payoff ratio
  loop/
    main.py             # background loop: poll price -> run strategies ->
                         # size via Kelly -> execute via broker -> log to DB
                         # -> sleep 5 min
  dashboard/
    app.py               # Streamlit; reads SQLite only, no direct coupling
                          # to the loop process
tests/
  test_broker.py         # fee/slippage math
  test_kelly.py           # Kelly formula
  test_backtest.py        # scoring/pass-fail logic
```

## Data flow

1. `loop/main.py` polls Binance public REST for current BTC/ETH/SOL price.
2. Each active strategy scores a signal from recent price history.
3. If a strategy signals entry/exit, `sizing/kelly.py` computes fractional
   Kelly position size from that strategy's backtested win rate/payoff.
4. `engine/broker.py` executes the trade against `engine/portfolio.py`,
   applying real fee + slippage, and writes to `engine/db.py` (SQLite).
5. `dashboard/app.py` reads the same SQLite file on a refresh interval and
   renders equity curve, open positions, and trade log. No IPC between loop
   and dashboard beyond the DB file.

## Error handling

- Price fetch failure: log the error, skip this cycle, never substitute a
  cached/fabricated price silently.
- Strategy fails backtest pass criteria: excluded from live trading; reason
  is logged and shown in the dashboard (e.g. "SMA cross: Sharpe -0.2, rejected").
- Broker cannot fill (e.g. balance insufficient): trade rejected, logged,
  never silently resized or invented.

## Testing

- Unit tests for fee/slippage math against a documented formula (Binance
  spot taker fee = 0.1%, confirmed via official docs during implementation).
- Unit test for fractional Kelly formula against the standard definition
  `f* = (bp - q) / b` scaled by a fraction (e.g. 0.5x Kelly) for safety.
- Unit test for backtest scoring (Sharpe, max drawdown, pass/fail threshold).
- Manual verification: run one full honest cycle (fetch price → open trade →
  close trade) and inspect the DB row by hand before trusting the loop.

## Open questions / risks

- Binance public API rate limits: need to confirm current limits during
  implementation (per guide's "verify, don't guess" rule) and set poll
  interval accordingly.
- Backtest historical data source for BTC/ETH/SOL candles still to be
  chosen during implementation (likely Binance klines endpoint, also free).
