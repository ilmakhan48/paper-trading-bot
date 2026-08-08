# Periodic Strategy Re-vetting — Design Spec

Date: 2026-07-06

## Purpose

Make the bot "learn from its mistakes" on the existing spot paper-trading
bot: instead of vetting each strategy against historical data once at
startup and trusting that decision forever, periodically re-check each
strategy against fresh recent price history. A strategy that starts losing
its edge gets demoted (stops opening new positions); a previously-rejected
strategy that starts looking good gets promoted. This replaces nothing —
it's an addition to the existing background loop
(`tradingbot/loop/main.py`), which already runs, is tested, and works.

Explicitly not in scope: the leverage/margin engine, episodes/reset, or
"evolution" (auto-tuning leverage/Kelly fraction) explored earlier in this
session — those are set aside. This is a small, contained addition to the
spot bot only.

## Scope

- Re-run the existing `vet_strategies()` logic every 72 cycles (6 hours at
  the existing 5-minute poll interval), on fresh 500-candle hourly history
  — same backtest gate (`sharpe > 0`, `max_drawdown < 0.5`, `num_trades >=
  2`) already built and approved.
- Each re-vet logs new rows to the existing `strategy_runs` table (no
  schema change) — the dashboard's existing "Strategy Vetting" section
  will show the updated history automatically, no dashboard change needed.
- A strategy/symbol combo that passes re-vetting after previously failing
  is promoted: eligible to open new positions again.
- A strategy/symbol combo that fails re-vetting after previously passing
  is demoted: blocked from opening new positions, but still evaluated for
  signals on any symbol where it currently holds an open position, so that
  position can close honestly on its own exit signal rather than being
  silently orphaned.
- `price_history` (the live-polled series used for signal evaluation)
  is untouched by this change — re-vetting uses a fresh, separate fetch of
  historical klines, exactly like the original startup vetting does.

## Out of scope

- Any change to `tradingbot/engine/`, `tradingbot/strategies/`,
  `tradingbot/backtest/`, `tradingbot/sizing/`, or the dashboard.
- The margin/leverage engine (`tradingbot/margin/`) — untouched, unused by
  this change.
- Forced early close of a demoted strategy's open position (explicitly
  rejected in favor of letting it close on its own signal).

## Architecture

All changes live in `tradingbot/loop/main.py`:

- `vet_strategies(conn)` (already exists) is called again periodically,
  not just once at startup.
- A new cycle counter tracks when 72 cycles have elapsed since the last
  vetting pass (initial vetting at startup counts as the first pass).
- `approved_strategies` (the list controlling which strategy/symbol combos
  can open new positions) is replaced with each re-vet's fresh result.
- A new helper determines, for each cycle, the full set of (symbol,
  strategy) pairs to evaluate a signal for: the currently-approved set,
  plus any (symbol, strategy_name) pair that has an open trade in the DB
  (via `get_open_trades`) whose strategy isn't in the currently-approved
  set — using the matching strategy object from the existing
  `ALL_STRATEGIES` list looked up by name. Only pairs in the
  currently-approved set are allowed to *open* a new position; all pairs
  in the full evaluate-set are allowed to *close* one.

## Data flow

1. At startup: `vet_strategies(conn)` runs once (as today), producing
   `approved_strategies` and the seeded `price_history`. Cycle counter
   starts at 0.
2. Each cycle: if the counter has reached 72 since the last vetting pass,
   call `vet_strategies(conn)` again (fresh klines, fresh backtest, new
   `strategy_runs` rows logged), replace `approved_strategies` with the new
   result, and reset the counter. `price_history`'s existing continuously-
   polled series is untouched by this — it keeps accumulating exactly as
   before.
3. Every cycle (unchanged otherwise): poll live prices, build the full
   evaluate-set (approved ∪ open-position holders per the rule above),
   evaluate each pair's signal, open new positions only for approved pairs
   with no open position, close positions on a sell signal for *any* pair
   in the evaluate-set (approved or demoted), log equity, sleep.

## Error handling

- A re-vet's klines fetch failure (`PriceFetchError`) is handled the same
  way `vet_strategies()` already handles it at startup — if fetching fails
  for a symbol, that symbol's re-vetting is skipped for this pass and the
  previous approval status for that symbol's strategies is kept unchanged
  until the next successful re-vet, rather than defaulting to
  approved-with-no-evidence or crashing the loop.
- Demoted strategies never open new positions even if a stale reference to
  them lingers anywhere — the open/close gating is based on the
  currently-approved set checked fresh each cycle, not a one-time snapshot.

## Testing

- Unit test: after 72 cycles, `vet_strategies` is called again (verify via
  a call-count assertion on a mocked/stubbed vetting function, or by
  checking a fresh `strategy_runs` row appears).
- Unit test: a strategy/symbol combo present in `approved_strategies` but
  with no open position is correctly excluded from opening once removed
  from a fresh re-vet result.
- Unit test: a strategy/symbol combo removed from `approved_strategies` but
  with an existing open trade for that symbol/strategy is still included
  in the evaluate-set (so its sell signal can still be checked and can
  close the position).
- Manual smoke test: confirm the real vetting call happens correctly
  against live Binance data (same pattern as the original loop's Task 9
  smoke test), and that a shortened cycle threshold (e.g. patched down to
  2-3 cycles for the test run) actually triggers a second `vet_strategies`
  call and updates `approved_strategies`.

## Open questions / risks

- None outstanding — this is a small, additive change to an already-
  working, already-reviewed module.
