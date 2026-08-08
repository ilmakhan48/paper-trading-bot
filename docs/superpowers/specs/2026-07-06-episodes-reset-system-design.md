# Episodes / Reset System — Design Spec

Date: 2026-07-06

## Purpose

Add an episode/reset game loop on top of the leverage/margin engine
(sub-project 1): each episode starts fresh with a small stake, trades
long/short with leverage, and ends when it hits a goal, blows up, or times
out — then a new episode starts automatically. This is sub-project 2 of 4
(episodes → evolution → dashboard). Same honesty rule as the rest of the
project: every equity check, liquidation, and close uses real numbers, never
fabricated.

## Scope

- New `tradingbot/episodes/` package, standalone from the existing spot
  engine (`tradingbot/engine/`), which keeps running unaffected as its own
  continuous mode.
- Built entirely on the existing leverage/margin engine
  (`tradingbot/margin/`, already implemented and reviewed) — no changes to
  `margin/portfolio.py`, `margin/broker.py`, `margin/db.py`, or
  `margin/funding.py`.
- Reuses existing strategies (`tradingbot/strategies/`), backtester
  (`tradingbot/backtest/runner.py`), and sizing
  (`tradingbot/sizing/kelly.py`) as-is — no changes.
- Each episode: starting cash **$100**, goal **$500** (5x), fixed
  **10x leverage**, fixed strategy set (SMA cross, RSI, momentum — same
  three as the spot bot), simultaneous positions across BTC/ETH/SOL
  allowed.
- Episode ends on: **goal** (equity ≥ $500), **blowup** (equity ≤ $20, 20%
  of start), or **timeout** (200 cycles at the existing 5-minute poll
  interval, ≈16.7 hours) — whichever comes first.
- On episode end, any still-open positions are honestly closed at the
  current live mark price (never silently dropped or left stale) before a
  brand-new episode starts automatically with a fresh $100.
- New `episodes` SQLite table logging each run's outcome and history.

## Out of scope (future sub-projects)

- Strategy/leverage "evolution" across episodes (promote/demote strategies,
  retune leverage or Kelly fraction based on past outcomes) — sub-project 3.
- Multi-page dashboard visualizing episodes/evolution — sub-project 4.
- Changing anything about the spot engine or the margin engine's own
  modules (this plan only adds a new consumer on top of them).

## Architecture

```
tradingbot/episodes/
  __init__.py
  db.py       # episodes table + CRUD
  runner.py   # drives one episode's full lifecycle; run_forever() loops
              # episodes indefinitely
```

Data flow: `runner.py` vets each strategy per symbol via the existing
`backtest.run_backtest` (same pattern as the spot loop's `vet_strategies`),
then drives cycles: poll live mark price per symbol (`margin.funding.
get_mark_price`) → check each open position for liquidation
(`MarginBroker.check_liquidation`) → compute portfolio-wide equity (cash +
unrealized PnL across open positions) → check blowup floor → check goal →
if neither, evaluate approved strategies for new buy/sell signals and open
long/short positions via `MarginBroker.open_position`, sized by
`sizing.kelly.position_size(equity, win_rate, payoff_ratio)` as **margin**
dollars, with `notional = margin * leverage` → apply funding on Binance's
real 8-hour schedule → log equity → sleep 5 minutes → repeat, until goal/
blowup/timeout, then honestly close any open positions and start a new
episode.

## Data model

`episodes` table:
- `id`, `start_balance` (100.0), `goal` (500.0), `status`
  (`"running"` | `"goal"` | `"blowup"` | `"timeout"`)
- `started_at`, `ended_at`
- `peak_equity` (highest equity seen during the episode, for the "peak
  $X" style history the reference showed)
- `final_equity`
- `cycles_run`

## Cycle logic (per episode, per 5-minute cycle)

1. Poll live mark price for each symbol with an open position or a
   candidate signal (same fetch-failure handling as the spot loop: skip
   that symbol this cycle, never substitute a fake price).
2. For each open position, call `MarginBroker.check_liquidation` — if
   breached, it force-closes at the liquidation price and flags
   `liquidated=True` (already built in sub-project 1).
3. Compute portfolio-wide equity: `cash + sum(qty * (mark_price - entry) for
   longs) + sum(qty * (entry - mark_price) for shorts)` across all
   remaining open positions.
4. If `equity <= 0.2 * start_balance` (blowup floor): close any remaining
   open positions honestly at their live mark price, mark the episode
   `status="blowup"`, log `final_equity`/`ended_at`.
5. Else if `equity >= goal`: close any remaining open positions honestly,
   mark `status="goal"`.
6. Else if `cycles_run >= 200`: close any remaining open positions
   honestly, mark `status="timeout"`.
7. Else (episode continues): for each symbol whose strategy passed
   vetting, evaluate its signal against price history; on a fresh buy
   signal with no open position in that symbol, open a **long**; on a
   fresh sell signal with no open position, open a **short** — sized via
   `position_size(equity, win_rate, payoff_ratio)` as margin dollars,
   `notional = margin * 10` (leverage).
8. Apply funding to open positions when Binance's real funding schedule
   crosses an 8-hour boundary (checked via the real funding rate feed —
   never applied on a guessed schedule).
9. Log `equity` this cycle, update `peak_equity` if it's a new high,
   increment `cycles_run`, sleep 5 minutes.

On any end condition (steps 4-6), after logging the episode's outcome,
`run_forever()` immediately starts a new episode with a fresh
`MarginPortfolio(cash=100)`.

## Error handling

- Mark price fetch failure: skip that symbol this cycle only (matches the
  spot loop's and margin engine's existing pattern) — never crashes the
  episode or substitutes a stale/fake price.
- Funding rate fetch failure: skip applying funding this cycle, try again
  next cycle — never silently zero out or fabricate a funding payment.
- If a symbol has no approved (backtest-passing) strategy, it simply never
  trades that episode — consistent with the spot loop's honesty rule that
  an unvetted strategy never goes live.

## Testing

- Unit tests for portfolio-wide equity calculation (long and short
  positions, mixed).
- Unit tests for blowup/goal/timeout detection thresholds (boundary values:
  exactly at goal, exactly at blowup floor, exactly at cycle 200).
- Unit test for episodes DB CRUD (insert running episode, update to
  goal/blowup/timeout with final numbers).
- Unit test that a fresh episode starts with `cash=100.0` and no open
  positions, immediately after the previous episode ends.
- Manual smoke test against real Binance data: run a capped, short-lived
  episode (a handful of real cycles, not the full 200) and confirm it
  vets strategies, polls real prices, and would transition states
  correctly — mirroring how sub-project 1's Task 5 and the original spot
  loop's Task 9 were verified.

## Open questions / risks

- Funding's real 8-hour boundary check needs the exact schedule
  (Binance funding times are fixed UTC hours) confirmed at implementation
  time, same verify-don't-guess posture as sub-project 1.
- This system runs independently of the existing spot loop and dashboard —
  it does not yet have its own dashboard view (sub-project 4) or feed into
  "evolution" (sub-project 3); until those exist, episode history is only
  visible by querying the `episodes` table directly.
