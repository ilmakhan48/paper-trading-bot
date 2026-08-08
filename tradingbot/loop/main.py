# tradingbot/loop/main.py
import time
from datetime import datetime, timezone

import requests

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
REVET_INTERVAL_CYCLES = 72  # 6 hours at the 300-second poll interval
STARTING_CASH = 10000.0
DB_PATH = "tradingbot.db"

ALL_STRATEGIES = [SmaCrossStrategy(), RsiStrategy(), MomentumStrategy()]


MAX_PAYOFF_RATIO = 5.0  # cap when a backtest sample has zero losing trades


def _win_rate_and_payoff(result):
    """Derive real win_rate/payoff_ratio from the backtest's actual trade-by-trade PnL."""
    trade_pnls = result.trade_pnls
    if not trade_pnls:
        return 0.0, 0.0
    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p <= 0]
    win_rate = len(wins) / len(trade_pnls)
    if wins and losses:
        avg_win = sum(wins) / len(wins)
        avg_loss = sum(abs(p) for p in losses) / len(losses)
        payoff_ratio = min(avg_win / avg_loss, MAX_PAYOFF_RATIO) if avg_loss > 0 else MAX_PAYOFF_RATIO
    elif wins and not losses:
        payoff_ratio = MAX_PAYOFF_RATIO
    else:
        payoff_ratio = 0.0
    return win_rate, payoff_ratio


def vet_strategies(conn):
    """Backtest each strategy per symbol on 1h history; only passing ones trade live.

    Returns (approved_strategies, history_seed) where history_seed maps each symbol to
    the 1h closes used for backtesting, so live trading can continue that same series
    rather than starting from an empty price history.
    """
    approved = []
    history_seed: dict[str, list[float]] = {}
    for symbol in SYMBOLS:
        klines = get_klines(symbol, "1h", 500)
        closes = [k["close"] for k in klines]
        history_seed[symbol] = list(closes)
        for strategy in ALL_STRATEGIES:
            result = run_backtest(strategy, closes)
            insert_strategy_run(
                conn, strategy=f"{strategy.name}:{symbol}", passed=result.passed,
                sharpe=result.sharpe, max_drawdown=result.max_drawdown, reason=result.reason,
                run_at=datetime.now(timezone.utc).isoformat(),
            )
            if result.passed:
                win_rate, payoff_ratio = _win_rate_and_payoff(result)
                approved.append((symbol, strategy, win_rate, payoff_ratio))
    return approved, history_seed


def maybe_revet(conn, cycles_since_vet, approved_strategies,
                 vet_fn=vet_strategies, revet_interval=REVET_INTERVAL_CYCLES):
    """Re-run vet_fn every `revet_interval` cycles; otherwise pass through unchanged.

    Returns (approved_strategies, cycles_since_vet) for the caller to carry
    into the next cycle.
    """
    cycles_since_vet += 1
    if cycles_since_vet < revet_interval:
        return approved_strategies, cycles_since_vet
    try:
        new_approved, _ = vet_fn(conn)
    except (PriceFetchError, requests.exceptions.RequestException) as exc:
        now = datetime.now(timezone.utc).isoformat()
        print(f"[{now}] re-vet failed: {exc!r} — keeping current approvals, will retry next interval")
        return approved_strategies, 0
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


if __name__ == "__main__":
    main()
