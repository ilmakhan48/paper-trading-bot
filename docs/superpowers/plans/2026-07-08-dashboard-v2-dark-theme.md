# Dashboard v2 (Dark Terminal Theme) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the existing Streamlit dashboard (`tradingbot/dashboard/app.py`) from its light "paper ledger" theme to a dark trading-terminal theme, and add three functional upgrades: per-coin sparklines, P&L color-coded open-position cards, and an auto-refresh toggle.

**Architecture:** All changes live in two files: `tradingbot/dashboard/app.py` (color constants, CSS block, header markup, coin-card/ticket-card rendering, equity chart, new toggle) and `.streamlit/config.toml` (Streamlit's own theme keys, kept in sync with the hardcoded palette). No new files, no new pip dependencies, no changes to any other module.

**Tech Stack:** Python 3.9 (`.venv312`), Streamlit, Altair, pandas — all already in use in this file. Reuses `tradingbot.data.binance_feed.get_klines` (already used by `tradingbot/loop/main.py`) for the sparkline data.

## Global Constraints

- Dark palette (exact values, from the approved spec): background `#0B0F14`, primary text `#E7ECF1`, secondary/muted text `#7C8B99`, gain/up `#2DD48A`, loss/down `#FF5A5A`, amber (invested bar) `#E0A83E`, hairline/rule `rgba(255,255,255,0.08)`.
- Header text is exactly: `Ilma Khanum's Trading Bot` followed by a `LIVE` badge, then the existing subtitle line unchanged: `real prices, fake money, and it never lies.`
- Sparklines use `get_klines(symbol, "1h", 24)` — 24 hourly candles, no other window.
- Auto-refresh interval is exactly 30 seconds, toggle defaults to **off**.
- No new pip dependencies. No changes to `tradingbot/engine/`, `tradingbot/loop/`, `tradingbot/strategies/`, `tradingbot/backtest/`, `tradingbot/sizing/`, `tradingbot/margin/`, or the DB schema.
- Section order on the page is unchanged: wallet → by-coin → equity → open positions → trade log → strategy vetting.
- This file (`tradingbot/dashboard/app.py`) has no existing unit test suite — it's a Streamlit script, not an importable library module, consistent with how the original dashboard was verified. Per-task verification is `python -m py_compile` (catches syntax errors) plus a precise manual browser check described in each task. The final task adds a Playwright full-page screenshot check, matching the verification pattern used for the original dashboard redesign in this project.
- Any sparkline fetch failure for a symbol must render that card without a fabricated/stale line and show a small "sparkline unavailable" note instead — never silently draw a fake trend.

---

## Current file reference (before this plan's changes)

`tradingbot/dashboard/app.py` is 349 lines. The sections this plan touches, by their current line numbers:
- Lines 27-32: color constants (`INK`, `PAPER`, `GAIN`, `LOSS`, `AMBER`, `RULE`).
- Lines 36-170: the `<style>` CSS block.
- Lines 172-177: header markup (title, subtitle, rule).
- Lines 270-295: "BY COIN" card loop.
- Lines 297-313: "EQUITY CURVE" chart.
- Lines 315-334: "OPEN POSITIONS" ticket loop.

`.streamlit/config.toml` is currently:
```toml
[theme]
base = "light"
primaryColor = "#2F6F5E"
backgroundColor = "#EEF1F4"
secondaryBackgroundColor = "#E2E7EB"
textColor = "#1C2B39"
font = "monospace"

[server]
headless = true
```

---

### Task 1: Dark theme foundation (colors, CSS, header, Streamlit config)

**Files:**
- Modify: `tradingbot/dashboard/app.py:27-32` (color constants)
- Modify: `tradingbot/dashboard/app.py:36-170` (CSS block)
- Modify: `tradingbot/dashboard/app.py:172-177` (header markup)
- Modify: `.streamlit/config.toml` (full file)

**Interfaces:**
- Produces: color constants `INK`, `PAPER`, `GAIN`, `LOSS`, `AMBER`, `RULE` (module-level strings in `app.py`) — later tasks (2, 3, 4) reference these by name for chart colors and inline styles. `RULE` becomes `"rgba(255,255,255,0.08)"` (no longer a hex string) — tasks that use it as an Altair axis color must pass it as-is, Altair accepts CSS color strings including `rgba()`.
- Produces: CSS class `.badge` — used only in this task's header markup.

- [ ] **Step 1: Replace the color constants**

In `tradingbot/dashboard/app.py`, replace lines 27-32:

```python
INK = "#1C2B39"
PAPER = "#EEF1F4"
GAIN = "#2F6F5E"
LOSS = "#B5482E"
AMBER = "#C98A2C"
RULE = "#B9C2CA"
```

with:

```python
INK = "#E7ECF1"
PAPER = "#0B0F14"
GAIN = "#2DD48A"
LOSS = "#FF5A5A"
AMBER = "#E0A83E"
RULE = "rgba(255,255,255,0.08)"
```

- [ ] **Step 2: Replace the CSS block**

Replace the entire `<style>...</style>` block currently at lines 38-167 (inside the `st.markdown(""" ... """, unsafe_allow_html=True)` call spanning lines 36-170) with:

```css
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@600;700&family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600&display=swap');

    html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }

    .stApp { background-color: #0B0F14; }

    .ledger-title {
        font-family: 'Source Serif 4', serif;
        font-weight: 700;
        font-size: 2.4rem;
        color: #E7ECF1;
        margin-bottom: 0;
        letter-spacing: -0.01em;
    }
    .ledger-sub {
        font-family: 'Inter', sans-serif;
        color: #7C8B99;
        font-size: 0.95rem;
        margin-top: 0.2rem;
    }
    .ledger-rule {
        border: none;
        border-top: 2px solid rgba(255,255,255,0.15);
        margin: 0.6rem 0 1.4rem 0;
    }
    .ledger-rule::after {
        content: "";
    }
    .num {
        font-family: 'JetBrains Mono', monospace;
        font-variant-numeric: tabular-nums;
    }

    .badge {
        display: inline-block;
        font-family: 'Inter', sans-serif;
        font-size: 0.65rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        padding: 2px 8px;
        border-radius: 20px;
        background: rgba(45,212,138,0.15);
        color: #2DD48A;
        margin-left: 8px;
        vertical-align: middle;
    }

    .wallet-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 6px;
        padding: 1rem 1.2rem;
        height: 100%;
    }
    .wallet-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #7C8B99;
        margin-bottom: 0.3rem;
    }
    .wallet-value {
        font-family: 'JetBrains Mono', monospace;
        font-variant-numeric: tabular-nums;
        font-size: 1.6rem;
        font-weight: 700;
        color: #E7ECF1;
    }
    .wallet-bar-track {
        background: rgba(255,255,255,0.08);
        border-radius: 4px;
        height: 6px;
        margin-top: 0.5rem;
        overflow: hidden;
    }
    .wallet-bar-fill {
        height: 6px;
        border-radius: 4px;
    }

    .gain { color: #2DD48A; }
    .loss { color: #FF5A5A; }
    .neutral { color: #7C8B99; }

    .coin-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 6px;
        padding: 0.9rem 1.1rem;
    }
    .coin-symbol {
        font-family: 'Source Serif 4', serif;
        font-weight: 700;
        font-size: 1.15rem;
        color: #E7ECF1;
    }
    .coin-row {
        display: flex;
        justify-content: space-between;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        color: #B7C2CC;
        margin-top: 0.3rem;
    }

    .ticket {
        background: rgba(255,255,255,0.02);
        border: 1px dashed rgba(255,255,255,0.15);
        border-radius: 4px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.7rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        position: relative;
    }
    .ticket::before {
        content: "TICKET";
        position: absolute;
        top: -0.55rem;
        left: 0.8rem;
        background: #0B0F14;
        padding: 0 0.4rem;
        font-family: 'Inter', sans-serif;
        font-size: 0.65rem;
        letter-spacing: 0.1em;
        color: #7C8B99;
    }
    .ticket-row {
        display: flex;
        justify-content: space-between;
        padding: 0.1rem 0;
    }
    .ticket-symbol {
        font-family: 'Source Serif 4', serif;
        font-weight: 700;
        font-size: 1rem;
        color: #E7ECF1;
    }

    section[data-testid="stDataFrame"] * {
        font-family: 'JetBrains Mono', monospace !important;
        font-variant-numeric: tabular-nums;
    }
    </style>
```

- [ ] **Step 3: Replace the header markup**

Replace lines 172-177:

```python
st.markdown('<div class="ledger-title">Paper Trading Bot — Ledger</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="ledger-sub">real prices, fake money, and it never lies.</div>',
    unsafe_allow_html=True,
)
st.markdown('<hr class="ledger-rule">', unsafe_allow_html=True)
```

with:

```python
st.markdown(
    '<div class="ledger-title">Ilma Khanum\'s Trading Bot <span class="badge">LIVE</span></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="ledger-sub">real prices, fake money, and it never lies.</div>',
    unsafe_allow_html=True,
)
st.markdown('<hr class="ledger-rule">', unsafe_allow_html=True)
```

- [ ] **Step 4: Replace `.streamlit/config.toml`**

Replace the full file contents with:

```toml
[theme]
base = "dark"
primaryColor = "#2DD48A"
backgroundColor = "#0B0F14"
secondaryBackgroundColor = "#131A22"
textColor = "#E7ECF1"
font = "monospace"

[server]
headless = true
```

- [ ] **Step 5: Verify syntax**

Run: `.venv312/bin/python -m py_compile "tradingbot/dashboard/app.py"`
Expected: no output, exit code 0.

- [ ] **Step 6: Manual browser check**

Run: `.venv312/bin/streamlit run tradingbot/dashboard/app.py`

Open the printed local URL. Confirm:
- Page background is near-black (`#0B0F14`), not white.
- Title reads "Ilma Khanum's Trading Bot" with a small green "LIVE" pill badge next to it.
- Subtitle below it still reads "real prices, fake money, and it never lies."
- Wallet cards, coin cards, and ticket cards render as dark translucent panels with light text — no leftover white/light backgrounds.

Stop the streamlit process (Ctrl+C) after confirming.

- [ ] **Step 7: Commit**

```bash
git add tradingbot/dashboard/app.py .streamlit/config.toml
git commit -m "feat: restyle dashboard to dark terminal theme"
```

---

### Task 2: Per-coin sparklines

**Files:**
- Modify: `tradingbot/dashboard/app.py` (imports, add `pnl_class` helper, rewrite "BY COIN" loop at lines 270-295)

**Interfaces:**
- Consumes: `GAIN`, `LOSS` from Task 1.
- Produces: `pnl_class(value: float) -> str` — returns `"gain"` if `value >= 0` else `"loss"`. Task 3 reuses this exact function.

- [ ] **Step 1: Add `get_klines` to the existing import**

In `tradingbot/dashboard/app.py`, find:

```python
from tradingbot.data.binance_feed import get_price, PriceFetchError
```

Replace with:

```python
from tradingbot.data.binance_feed import get_price, get_klines, PriceFetchError
```

- [ ] **Step 2: Add the `pnl_class` helper**

Find:

```python
def fmt_signed(value: float) -> str:
    sign = "-" if value < 0 else "+"
    return f"{sign}${abs(value):,.2f}"
```

Add immediately after it:

```python
def pnl_class(value: float) -> str:
    return "gain" if value >= 0 else "loss"
```

- [ ] **Step 3: Rewrite the "BY COIN" loop with sparklines**

Replace lines 270-295 (from `st.markdown("<div style='height:1.2rem;'></div>", unsafe_allow_html=True)` through the end of the `for col, symbol in zip(...)` loop) with:

```python
st.markdown("<div style='height:1.2rem;'></div>", unsafe_allow_html=True)
st.markdown('<div class="wallet-label">BY COIN</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
for col, symbol in zip((c1, c2, c3), SYMBOLS):
    sym_open = [t for t in open_trades if t["symbol"] == symbol]
    sym_closed_today = [
        t for t in closed_trades
        if t["symbol"] == symbol and t["pnl"] is not None and t["closed_at"].startswith(today_str)
    ]
    sym_qty = sum(t["qty"] for t in sym_open)
    sym_invested = sum(t["qty"] * t["open_price"] + t["open_fee"] for t in sym_open)
    sym_unrealized = sum(
        t["qty"] * (live_prices.get(symbol, t["open_price"]) - t["open_price"]) for t in sym_open
    )
    sym_today_realized = sum(t["pnl"] for t in sym_closed_today)
    sym_pnl = sym_unrealized + sym_today_realized
    cls = pnl_class(sym_pnl)

    try:
        sparkline_klines = get_klines(symbol, "1h", 24)
    except PriceFetchError:
        sparkline_klines = None

    with col:
        st.markdown(
            f"""<div class="coin-card">
                <div class="coin-symbol">{symbol[:-4]}</div>
                <div class="coin-row"><span>position</span><span>{sym_qty:.6f}</span></div>
                <div class="coin-row"><span>invested</span><span>${sym_invested:,.2f}</span></div>
                <div class="coin-row"><span>today P&amp;L</span><span class="{cls}">{fmt_signed(sym_pnl)}</span></div>
            </div>""",
            unsafe_allow_html=True,
        )
        if sparkline_klines:
            spark_df = pd.DataFrame(sparkline_klines).reset_index()
            spark_first = spark_df["close"].iloc[0]
            spark_last = spark_df["close"].iloc[-1]
            spark_color = GAIN if spark_last >= spark_first else LOSS
            spark_chart = (
                alt.Chart(spark_df)
                .mark_line(color=spark_color, strokeWidth=2)
                .encode(
                    x=alt.X("index:Q", axis=None),
                    y=alt.Y("close:Q", axis=None, scale=alt.Scale(zero=False)),
                )
                .properties(height=40)
                .configure_view(strokeWidth=0)
            )
            st.altair_chart(spark_chart, use_container_width=True)
        else:
            st.caption("sparkline unavailable")
```

- [ ] **Step 4: Verify syntax**

Run: `.venv312/bin/python -m py_compile "tradingbot/dashboard/app.py"`
Expected: no output, exit code 0.

- [ ] **Step 5: Manual browser check**

Run: `.venv312/bin/streamlit run tradingbot/dashboard/app.py`

Confirm under each of the BTC/ETH/SOL cards a small line-chart sparkline renders below the existing rows, colored green if that coin's price rose over the last 24 hourly candles or red if it fell. If the network is unreachable for a symbol, that card shows "sparkline unavailable" instead of a chart or an error.

Stop the streamlit process (Ctrl+C) after confirming.

- [ ] **Step 6: Commit**

```bash
git add tradingbot/dashboard/app.py
git commit -m "feat: add 24h sparklines to coin cards"
```

---

### Task 3: Color-coded open position cards

**Files:**
- Modify: `tradingbot/dashboard/app.py` (rewrite "OPEN POSITIONS" loop at lines 315-334)

**Interfaces:**
- Consumes: `pnl_class(value: float) -> str` from Task 2, `GAIN`/`LOSS` from Task 1.

- [ ] **Step 1: Rewrite the "OPEN POSITIONS" loop**

Replace lines 315-334 (from `st.markdown("<div style='height:1.2rem;'></div>", unsafe_allow_html=True)` before "OPEN POSITIONS" through the `else: st.write("No open positions.")`) with:

```python
st.markdown("<div style='height:1.2rem;'></div>", unsafe_allow_html=True)
st.markdown('<div class="wallet-label">OPEN POSITIONS</div>', unsafe_allow_html=True)
if open_trades:
    for t in open_trades:
        mark_price = live_prices.get(t["symbol"], t["open_price"])
        pos_pnl = t["qty"] * (mark_price - t["open_price"])
        cls = pnl_class(pos_pnl)
        accent = GAIN if cls == "gain" else LOSS
        glow = "rgba(45,212,138,0.08)" if cls == "gain" else "rgba(255,90,90,0.08)"
        st.markdown(
            f"""<div class="ticket" style="border-left:4px solid {accent}; box-shadow: inset 0 0 24px {glow};">
                <div class="ticket-row"><span class="ticket-symbol">{t['symbol']}</span><span>{t['strategy']}</span></div>
                <div class="ticket-row"><span>qty</span><span>{t['qty']:.6f}</span></div>
                <div class="ticket-row"><span>entry</span><span>${t['open_price']:,.2f}</span></div>
                <div class="ticket-row"><span>mark</span><span>${mark_price:,.2f}</span></div>
                <div class="ticket-row"><span>opened</span><span>{t['opened_at']}</span></div>
                <div class="ticket-row"><span>unrealized</span><span class="{cls}">{fmt_signed(pos_pnl)}</span></div>
            </div>""",
            unsafe_allow_html=True,
        )
else:
    st.write("No open positions.")
```

- [ ] **Step 2: Verify syntax**

Run: `.venv312/bin/python -m py_compile "tradingbot/dashboard/app.py"`
Expected: no output, exit code 0.

- [ ] **Step 3: Manual browser check**

Run: `.venv312/bin/streamlit run tradingbot/dashboard/app.py`

If there's at least one open position (check with `sqlite3 tradingbot.db "select * from trades where closed_at is null"` if unsure), confirm its ticket card has a colored left border (green if unrealized P&L ≥ 0, red if negative) and a matching subtle inset glow tint. If there are no open positions, confirm "No open positions." still renders correctly (no crash).

Stop the streamlit process (Ctrl+C) after confirming.

- [ ] **Step 4: Commit**

```bash
git add tradingbot/dashboard/app.py
git commit -m "feat: color-code open position cards by unrealized P&L"
```

---

### Task 4: Gradient-filled equity chart

**Files:**
- Modify: `tradingbot/dashboard/app.py` (rewrite "EQUITY CURVE" section at lines 297-313)

**Interfaces:**
- Consumes: `GAIN`, `PAPER`, `RULE`, `INK` from Task 1.

- [ ] **Step 1: Rewrite the equity chart**

Replace lines 297-313 (from `st.markdown("<div style='height:1.6rem;'></div>", unsafe_allow_html=True)` before "EQUITY CURVE" through the `else: st.info(...)`) with:

```python
st.markdown("<div style='height:1.6rem;'></div>", unsafe_allow_html=True)
st.markdown('<div class="wallet-label">EQUITY CURVE</div>', unsafe_allow_html=True)
if equity_history:
    df = pd.DataFrame(equity_history)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    line = (
        alt.Chart(df)
        .mark_line(color=GAIN, strokeWidth=2.5)
        .encode(
            x=alt.X("timestamp:T", title=None, axis=alt.Axis(gridColor=RULE, domainColor=RULE, labelColor=INK)),
            y=alt.Y("equity:Q", title="equity ($)", axis=alt.Axis(gridColor=RULE, domainColor=RULE, labelColor=INK)),
        )
    )
    area = (
        alt.Chart(df)
        .mark_area(
            line=False,
            color=alt.Gradient(
                gradient="linear",
                stops=[
                    alt.GradientStop(color="rgba(45,212,138,0.35)", offset=0),
                    alt.GradientStop(color="rgba(45,212,138,0.0)", offset=1),
                ],
                x1=1, x2=1, y1=1, y2=0,
            ),
        )
        .encode(
            x=alt.X("timestamp:T"),
            y=alt.Y("equity:Q"),
        )
    )
    chart = (area + line).properties(height=260, background=PAPER)
    st.altair_chart(chart, use_container_width=True)
else:
    st.info("No equity history yet — start the loop with `python -m tradingbot.loop.main`.")
```

- [ ] **Step 2: Verify syntax**

Run: `.venv312/bin/python -m py_compile "tradingbot/dashboard/app.py"`
Expected: no output, exit code 0.

- [ ] **Step 3: Manual browser check**

Run: `.venv312/bin/streamlit run tradingbot/dashboard/app.py`

Confirm the equity curve section shows a green line with a green gradient fill underneath it (fading to transparent toward the bottom), on the dark chart background, using the same `equity_history` data as before (compare the line's shape/values to what was shown before this task if easy to check — the numbers must be unchanged, only the rendering is different).

Stop the streamlit process (Ctrl+C) after confirming.

- [ ] **Step 4: Commit**

```bash
git add tradingbot/dashboard/app.py
git commit -m "feat: gradient-fill the equity curve chart"
```

---

### Task 5: Auto-refresh toggle

**Files:**
- Modify: `tradingbot/dashboard/app.py` (insert toggle after header, before `conn = init_db(DB_PATH)`)

**Interfaces:**
- None — self-contained addition, no new shared names.

- [ ] **Step 1: Add the toggle**

Find:

```python
st.markdown('<hr class="ledger-rule">', unsafe_allow_html=True)

conn = init_db(DB_PATH)
```

Replace with:

```python
st.markdown('<hr class="ledger-rule">', unsafe_allow_html=True)

auto_refresh = st.checkbox("Auto-refresh every 30s", value=False)
if auto_refresh:
    st.markdown('<meta http-equiv="refresh" content="30">', unsafe_allow_html=True)

conn = init_db(DB_PATH)
```

- [ ] **Step 2: Verify syntax**

Run: `.venv312/bin/python -m py_compile "tradingbot/dashboard/app.py"`
Expected: no output, exit code 0.

- [ ] **Step 3: Manual browser check**

Run: `.venv312/bin/streamlit run tradingbot/dashboard/app.py`

Confirm an unchecked "Auto-refresh every 30s" checkbox appears just below the header rule. With it unchecked, reload behaves exactly as before (manual reload only). Check it, then wait roughly 30 seconds and confirm the browser tab reloads on its own (e.g. watch the browser's loading indicator, or note that any live-price-dependent value updates without you touching anything). Uncheck it and confirm auto-reloading stops.

Stop the streamlit process (Ctrl+C) after confirming.

- [ ] **Step 4: Commit**

```bash
git add tradingbot/dashboard/app.py
git commit -m "feat: add optional 30s auto-refresh toggle to dashboard"
```

---

### Task 6: Full-page verification (screenshot)

**Files:** None modified — verification only.

**Interfaces:** None.

- [ ] **Step 1: Start the dashboard**

Run: `.venv312/bin/streamlit run tradingbot/dashboard/app.py`

- [ ] **Step 2: Take a full-page screenshot**

Using the Playwright MCP tools (same approach used for the original dashboard redesign in this project): navigate to the local Streamlit URL, resize the viewport to at least 1200×2000 so the full page is captured (not just the visible viewport), and take a full-page screenshot.

- [ ] **Step 3: Visually confirm, from the screenshot**

- Dark background throughout, no leftover white panels.
- Header shows "Ilma Khanum's Trading Bot" with the green "LIVE" badge.
- All three coin cards show sparklines.
- Any open position ticket card shows a colored left border/glow matching its P&L sign.
- Equity curve shows the green gradient fill.
- Auto-refresh checkbox is visible and unchecked by default.
- No visible layout breakage (overlapping text, cut-off cards) and no red Streamlit error boxes on the page.

- [ ] **Step 4: Check browser console for errors**

Using the Playwright MCP console-messages tool, confirm there are no JavaScript errors logged.

- [ ] **Step 5: Stop the dashboard**

Stop the streamlit process (Ctrl+C or kill the background process started in Step 1).

No commit for this task — it's verification only, confirming Tasks 1-5's combined result.
