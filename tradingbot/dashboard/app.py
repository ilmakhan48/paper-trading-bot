import os
import sys
from datetime import datetime, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import altair as alt
import pandas as pd
import requests
import streamlit as st

from tradingbot.data.binance_feed import get_price, get_klines, PriceFetchError
from tradingbot.engine.db import (
    init_db, get_all_trades, get_open_trades, get_equity_history, get_strategy_runs,
)

DB_PATH = "tradingbot.db"
STARTING_CASH = 10000.0
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def fmt_signed(value: float) -> str:
    sign = "-" if value < 0 else "+"
    return f"{sign}${abs(value):,.2f}"

def pnl_class(value: float) -> str:
    return "gain" if value >= 0 else "loss"

INK = "#E7ECF1"
PAPER = "#0B0F14"
GAIN = "#2DD48A"
LOSS = "#FF5A5A"
AMBER = "#E0A83E"
RULE = "rgba(255,255,255,0.08)"

st.set_page_config(page_title="Paper Trading Bot", layout="wide")

st.markdown(
    """
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
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="ledger-title">Paper Trading Bot <span class="badge">LIVE</span></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="ledger-sub">real prices, fake money, and it never lies.</div>',
    unsafe_allow_html=True,
)
st.markdown('<hr class="ledger-rule">', unsafe_allow_html=True)

auto_refresh = st.checkbox("Auto-refresh every 30s", value=False)
if auto_refresh:
    st.markdown('<meta http-equiv="refresh" content="30">', unsafe_allow_html=True)

conn = init_db(DB_PATH)
all_trades = get_all_trades(conn)
open_trades = get_open_trades(conn)
equity_history = get_equity_history(conn)
strategy_runs = get_strategy_runs(conn)

live_prices: dict[str, float] = {}
price_errors: list[str] = []
symbols_needed = {t["symbol"] for t in open_trades} or set(SYMBOLS)
for symbol in symbols_needed:
    try:
        live_prices[symbol] = get_price(symbol)
    except (PriceFetchError, requests.exceptions.RequestException):
        price_errors.append(symbol)

closed_trades = [t for t in all_trades if t["closed_at"] is not None]
realized_pnl = sum(t["pnl"] for t in closed_trades if t["pnl"] is not None)

invested = 0.0
unrealized_pnl = 0.0
for t in open_trades:
    cost = t["qty"] * t["open_price"] + t["open_fee"]
    invested += cost
    mark_price = live_prices.get(t["symbol"], t["open_price"])
    unrealized_pnl += t["qty"] * (mark_price - t["open_price"])

cash = STARTING_CASH + realized_pnl - invested
total_equity = cash + invested + unrealized_pnl
total_pnl = realized_pnl + unrealized_pnl

today_str = datetime.now(timezone.utc).date().isoformat()
today_realized = sum(
    t["pnl"] for t in closed_trades
    if t["pnl"] is not None and t["closed_at"].startswith(today_str)
)
today_pnl = today_realized + unrealized_pnl

if price_errors:
    st.warning(
        f"Live price fetch failed for: {', '.join(price_errors)}. "
        "Unrealized P&L for those positions uses entry price (0 change) until the next successful fetch — never a fabricated number."
    )

st.markdown('<div class="wallet-label" style="font-size:0.85rem; margin-top:0.4rem;">WALLET</div>', unsafe_allow_html=True)
w1, w2, w3, w4 = st.columns(4)

cash_pct = int(round((cash / total_equity) * 100)) if total_equity > 0 else 0
invested_pct = 100 - cash_pct

with w1:
    st.markdown(
        f"""<div class="wallet-card">
            <div class="wallet-label">Cash (idle)</div>
            <div class="wallet-value">${cash:,.2f}</div>
            <div class="wallet-bar-track"><div class="wallet-bar-fill" style="width:{cash_pct}%; background:{GAIN};"></div></div>
            <div class="ledger-sub" style="margin-top:0.3rem;">{cash_pct}% of wallet</div>
        </div>""",
        unsafe_allow_html=True,
    )
with w2:
    st.markdown(
        f"""<div class="wallet-card">
            <div class="wallet-label">Invested (at cost)</div>
            <div class="wallet-value">${invested:,.2f}</div>
            <div class="wallet-bar-track"><div class="wallet-bar-fill" style="width:{invested_pct}%; background:{AMBER};"></div></div>
            <div class="ledger-sub" style="margin-top:0.3rem;">{invested_pct}% of wallet</div>
        </div>""",
        unsafe_allow_html=True,
    )
with w3:
    cls = "gain" if total_pnl >= 0 else "loss"
    st.markdown(
        f"""<div class="wallet-card">
            <div class="wallet-label">Total P&amp;L (realized + open)</div>
            <div class="wallet-value {cls}">{fmt_signed(total_pnl)}</div>
            <div class="ledger-sub" style="margin-top:0.3rem;">since $10,000.00 start</div>
        </div>""",
        unsafe_allow_html=True,
    )
with w4:
    cls = "gain" if today_pnl >= 0 else "loss"
    st.markdown(
        f"""<div class="wallet-card">
            <div class="wallet-label">Today's P&amp;L</div>
            <div class="wallet-value {cls}">{fmt_signed(today_pnl)}</div>
            <div class="ledger-sub" style="margin-top:0.3rem;">UTC {today_str}</div>
        </div>""",
        unsafe_allow_html=True,
    )

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
    except (PriceFetchError, requests.exceptions.RequestException):
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

st.markdown("<div style='height:1.2rem;'></div>", unsafe_allow_html=True)
st.markdown('<div class="wallet-label">TRADE LOG</div>', unsafe_allow_html=True)
if all_trades:
    st.dataframe(pd.DataFrame(all_trades), use_container_width=True)
else:
    st.write("No trades yet.")

st.markdown("<div style='height:1.2rem;'></div>", unsafe_allow_html=True)
st.markdown('<div class="wallet-label">STRATEGY VETTING (honest pass/fail)</div>', unsafe_allow_html=True)
if strategy_runs:
    st.dataframe(pd.DataFrame(strategy_runs), use_container_width=True)
else:
    st.write("No strategy backtests recorded yet.")
