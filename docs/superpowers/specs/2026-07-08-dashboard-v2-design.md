# Dashboard v2 — Dark Terminal Redesign — Design Spec

Date: 2026-07-08

## Purpose

Replace the current "paper ledger" light theme (`tradingbot/dashboard/app.py`)
with a dark trading-terminal look, and add three functional improvements:
per-coin sparklines, P&L-based color coding on open position cards, and an
auto-refresh toggle. Personalize the header with "Ilma Khanum." Same
underlying data and honesty rules as today — this is a visual and small
functional upgrade, not a data-model change.

## Scope

- Restyle `tradingbot/dashboard/app.py` and `.streamlit/config.toml` to a
  dark theme (`#0B0F14` background, `#E7ECF1` primary text, green `#2DD48A`
  / red `#FF5A5A` accents), Inter for text, JetBrains Mono for numbers —
  replacing the ink/paper palette entirely.
- Header becomes "Ilma Khanum's Trading Bot" with a "LIVE" badge and
  the existing subtitle line ("real prices, fake money, and it never
  lies.").
- Per-coin cards (BTC/ETH/SOL) gain a 24h sparkline: fetched via
  `get_klines(symbol, "1h", 24)`, one call per symbol per page load.
  Sparkline color/glow is green if the last close > first close in that
  24h window, red otherwise (same rule driving the card's tint).
- Open position "ticket" cards get a colored left border + subtle
  background glow (green/red) based on that position's unrealized P&L
  sign — same color logic already used for the P&L text, now also applied
  to the card itself. Ticket-style dashed border is kept, recolored for
  dark background.
- Equity chart becomes a gradient-filled area chart (line + fill fading to
  transparent) instead of a plain line, same `equity_history` data, no new
  computation.
- New auto-refresh toggle in the header area, off by default. When on, the
  page reruns every 30 seconds.
- Section order is unchanged (wallet → by-coin → equity → open positions →
  trade log → strategy vetting) — only visual treatment and the three
  additions above change.

## Out of scope

- Any change to `tradingbot/engine/`, `tradingbot/loop/`, `tradingbot/strategies/`,
  `tradingbot/backtest/`, `tradingbot/sizing/`, or the DB schema.
- The margin/leverage engine (`tradingbot/margin/`) — untouched, unused.
- Mobile-specific layout, CSV export, alerts — not requested.
- Changing what data is shown, beyond the sparkline addition — all P&L,
  wallet, and trade numbers keep their existing source and formulas.

## Architecture

All changes live in `tradingbot/dashboard/app.py` (styling + new sparkline
fetch + refresh toggle) and `.streamlit/config.toml` (theme colors).

- **Sparkline fetch**: reuse `tradingbot.data.binance_feed.get_klines`
  (already used by the loop's vetting) — no new data module needed. Wrap
  each call in the existing `PriceFetchError` handling pattern already
  used for `get_price`: on failure, that coin's card renders without a
  sparkline and shows a small inline notice, never a fabricated line.
- **Auto-refresh**: no new pip dependency. When the toggle is on, inject
  `<meta http-equiv="refresh" content="30">` via `st.markdown(...,
  unsafe_allow_html=True)` — a plain HTML tag that reloads the page every
  30 seconds, which re-runs the whole script and re-fetches live data
  exactly like a manual reload does today. When the toggle is off, the
  tag is omitted and the page behaves exactly as it does now. No
  `time.sleep`/`st.rerun()` polling loop, no blocked script thread.
- **Color/glow logic**: a single small helper
  `pnl_class(value: float) -> Literal["up", "down"]` (or reuse a
  gain/loss threshold at 0, consistent with existing `fmt_signed`/`gain`/
  `loss` CSS class logic) drives both text color and the new card
  tint/border/glow — one source of truth per card, not duplicated
  thresholds.

## Data flow

Unchanged from today except:

1. For each symbol in `SYMBOLS`, in addition to the existing live price
   fetch, fetch `get_klines(symbol, "1h", 24)` for the sparkline. Failure
   is isolated per symbol (existing `price_errors` pattern extended to
   cover sparkline fetch failures with its own notice, not blocking the
   rest of the page).
2. Render coin cards with sparkline SVG/chart (via Altair, matching the
   existing charting library already in use for the equity chart — no new
   charting dependency).
3. Render open position cards with the color/glow class from
   `pnl_class(unrealized_pnl)`.
4. If the auto-refresh toggle is on, the page reruns every 30 seconds via
   the loop described above; off by default so it behaves exactly like
   today unless the user opts in.

## Error handling

- Sparkline fetch failure for a symbol: card renders without the
  sparkline graphic and shows a small "sparkline unavailable" note —
  never a fabricated or stale-drawn line. Matches the existing
  `price_errors` honesty pattern already in the file.
- Auto-refresh toggle never suppresses or alters the existing
  `price_errors` warning banner — that check still runs every render.

## Testing

- Manual smoke test: run `streamlit run tradingbot/dashboard/app.py`,
  confirm dark theme renders, sparklines appear for all three coins under
  normal network conditions, open position cards tint correctly for both
  a winning and losing position (can verify losing case by temporarily
  reading a closed/losing trade or reasoning about the color logic against
  a known negative `unrealized_pnl` value), auto-refresh toggle flips the
  page every ~30s when enabled and does nothing extra when disabled.
- Verify via Playwright screenshot (same pattern used for the original
  dashboard redesign) — full-page screenshot at a resized viewport to
  confirm no visual/layout regressions and no console errors.
- No new unit tests required — this file has no existing test suite (it's
  a Streamlit script, not an importable library module), consistent with
  how the original dashboard build was verified.

## Open questions / risks

- None outstanding — this is a self-contained visual/UX change to an
  already-working, already-reviewed dashboard script, using only
  libraries already in the project (Streamlit, Altair, the existing
  Binance feed module).
