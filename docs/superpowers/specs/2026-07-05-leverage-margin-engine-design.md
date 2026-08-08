# Leverage/Margin Engine — Design Spec

Date: 2026-07-05

## Purpose

Add leveraged, isolated-margin trading (long and short) to the paper trading
bot, as the foundation for a future episode/reset system and strategy
"evolution" (both out of scope here — this is sub-project 1 of 4). Same
honesty rule as the rest of the project: never fake a price, fill, funding
rate, or liquidation.

## Scope

- New `tradingbot/margin/` package, fully separate from the existing spot
  engine (`tradingbot/engine/`), which is untouched and keeps working
  standalone.
- Isolated margin only (each position's own margin; only that position can
  be liquidated — the rest of the account is unaffected).
- Long and short positions, up to 20x leverage.
- Real funding rate from Binance's public futures API (no key needed),
  applied periodically like a real perpetual future.
- Liquidation price computed per position, checked against a live mark
  price each cycle; a breach force-closes the position at the liquidation
  price (not an ideal exit — this is deliberately worse than a voluntary
  close, matching real exchange behavior).
- New `margin_positions` SQLite table, separate from the existing `trades`
  table.

## Out of scope (future sub-projects)

- Episode/reset system (goal + blowup detection, auto-restart) — sub-project 2.
- Strategy "evolution" across episodes (promote/demote, retune leverage/Kelly
  fraction based on past outcomes) — sub-project 3.
- Multi-page dashboard (Overview/Positions/Episodes/Evolution/Strategies/
  World/Lessons/Trades) — sub-project 4.
- Cross margin.
- Wiring the margin engine into the existing background loop's strategy
  selection — this spec only builds the engine itself (portfolio, broker,
  funding), verified standalone. Loop integration is part of sub-project 2,
  once episodes give the loop a reason to choose spot vs. margin.

## Architecture

```
tradingbot/margin/
  __init__.py
  funding.py       # get_mark_price(symbol), get_funding_rate(symbol) -- real
                    # Binance futures public API, confirmed live during
                    # planning:
                    # https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT
                    # https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1
  db.py            # margin_positions table + CRUD, separate from
                    # tradingbot/engine/db.py's trades table
  portfolio.py      # MarginPortfolio: cash, open MarginPosition objects
                    # (symbol, side, qty, entry_price, leverage, margin,
                    # liquidation_price, funding_paid)
  broker.py         # MarginBroker: open/close positions, computes
                    # liquidation price on open, applies funding on a
                    # schedule, checks liquidation against a live mark
                    # price and force-closes at the liq price if breached
tests/
  test_funding.py
  test_margin_db.py
  test_margin_portfolio.py
  test_margin_broker.py
```

## Data model

`margin_positions` table:
- `id`, `symbol`, `side` (`"long"` | `"short"`), `qty`
- `entry_price`, `leverage` (int, 1-20), `margin` (dollars locked for this
  position, isolated)
- `liquidation_price` (computed at open, fixed for the life of the position
  unless margin is added later — adding margin is out of scope)
- `funding_paid` (running total, can be negative if the bot received funding)
- `opened_at`, `closed_at`, `close_price`, `pnl`, `liquidated` (bool — true
  if closed via forced liquidation rather than a strategy-driven close)

## Liquidation math

Standard isolated-margin approximation (matches how exchanges compute it
for their lowest maintenance-margin tier):

- Long: `liquidation_price = entry_price * (1 - 1/leverage + mmr)`
- Short: `liquidation_price = entry_price * (1 + 1/leverage - mmr)`

Where `mmr` is the maintenance margin rate. The exact current value for
Binance's lowest tier must be confirmed against Binance's official margin
tier documentation during implementation (per the project's verify-before-
using-a-number rule) rather than assumed — if it cannot be confirmed, the
implementer must say so plainly and pick a clearly-labeled placeholder
rather than silently guessing.

`notional = qty * entry_price`, `margin = notional / leverage`. A position
is liquidated when the live mark price crosses `liquidation_price` against
the position's side (mark price ≤ liq price for a long, ≥ liq price for a
short).

## Funding

Real funding rate fetched from Binance's public futures API
(`fundingRate` endpoint) and applied to open positions on Binance's real
funding schedule (every 8 hours, at fixed UTC times — confirmed during
implementation against Binance's funding documentation). Funding payment
per position: `notional * funding_rate`, sign depending on side (longs pay
shorts when the rate is positive, and vice versa — the exact sign
convention must be confirmed against Binance's documentation rather than
assumed). Funding is added to `funding_paid` and debited/credited from
`MarginPortfolio.cash` immediately — never deferred or estimated.

## Error handling

- Mark price or funding rate fetch failure: skip that check this cycle
  (same pattern as the spot engine's price-fetch failure handling) — never
  substitute a stale or fabricated number for a liquidation check.
- Insufficient cash to post the required isolated margin: reject the trade
  before opening it, same spirit as the spot engine's `InsufficientFundsError`.
- A position already flagged `liquidated` cannot be closed again through the
  normal close path — closing a liquidated position is a no-op with a clear
  error, not a silent double-accounting of PnL.

## Testing

- Unit tests for the liquidation price formula (long and short) against
  hand-computed values once the real MMR is confirmed.
- Unit tests for margin/notional math (`margin = notional / leverage`).
- Unit tests for funding payment sign and amount, using a mocked funding
  rate response (matching the spot engine's pattern of mocking
  `requests.get` in `tests/test_binance_feed.py`).
- Unit test for forced liquidation: a position whose mark price crosses its
  liquidation price is closed at exactly the liquidation price, flagged
  `liquidated=True`, and the resulting PnL matches the expected max loss
  for that leverage (approximately `-margin`, before fees/funding).
- Manual smoke test against real Binance futures endpoints (mark price,
  funding rate) for BTCUSDT, mirroring how the spot feed (Task 2) and loop
  (Task 9) were verified.

## Open questions / risks

- Exact current Binance maintenance margin rate for the lowest tier must be
  confirmed at implementation time (documented as a risk above, not
  silently guessed).
- Funding sign convention (who pays whom when the rate is positive) must be
  confirmed against Binance's official documentation at implementation time.
- This engine is not yet wired into the background loop or dashboard —
  intentionally deferred to sub-project 2, once episodes exist to decide
  when margin trading is used.
