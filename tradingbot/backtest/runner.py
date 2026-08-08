from dataclasses import dataclass, field

import numpy as np

FEE_RATE = 0.001


@dataclass
class BacktestResult:
    strategy: str
    total_pnl: float
    sharpe: float
    max_drawdown: float
    num_trades: int
    passed: bool
    reason: str
    trade_pnls: list[float] = field(default_factory=list)


def run_backtest(strategy, closes: list[float], starting_cash: float = 10000.0,
                   fee_rate: float = FEE_RATE) -> BacktestResult:
    cash = starting_cash
    position_qty = 0.0
    entry_price = 0.0
    cost_basis = 0.0
    equity_curve = [starting_cash]
    num_trades = 0
    trade_pnls: list[float] = []

    for i in range(1, len(closes) + 1):
        window = closes[:i]
        price = closes[i - 1]
        signal = strategy.signal(window)

        if signal == "buy" and position_qty == 0.0:
            spend = cash * 0.99  # keep a buffer for fees
            qty = spend / price
            fee = spend * fee_rate
            cash -= (spend + fee)
            position_qty = qty
            entry_price = price
            cost_basis = spend + fee  # total dollars committed to this round trip
            num_trades += 1
        elif signal == "sell" and position_qty > 0.0:
            proceeds = position_qty * price
            fee = proceeds * fee_rate
            cash += proceeds - fee
            trade_pnls.append((proceeds - fee) - cost_basis)
            position_qty = 0.0
            cost_basis = 0.0
            num_trades += 1

        equity = cash + position_qty * price
        equity_curve.append(equity)

    if position_qty > 0.0:
        # honest close at final price, no rounding away the mark-to-market
        proceeds = position_qty * closes[-1]
        fee = proceeds * fee_rate
        cash += proceeds - fee
        trade_pnls.append((proceeds - fee) - cost_basis)
        equity_curve.append(cash)
        num_trades += 1

    total_pnl = equity_curve[-1] - starting_cash

    if num_trades == 0:
        return BacktestResult(
            strategy=strategy.name, total_pnl=0.0, sharpe=0.0, max_drawdown=0.0,
            num_trades=0, passed=False, reason="No trades were triggered by this strategy",
            trade_pnls=[],
        )

    returns = np.diff(equity_curve) / equity_curve[:-1]
    sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(len(returns))) if np.std(returns) > 0 else 0.0

    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        drawdown = (peak - value) / peak
        max_drawdown = max(max_drawdown, drawdown)

    passed = sharpe > 0 and max_drawdown < 0.5 and num_trades >= 2
    reason = "passed" if passed else (
        f"Sharpe {sharpe:.2f} or drawdown {max_drawdown:.2f} did not meet the pass bar"
    )

    return BacktestResult(
        strategy=strategy.name, total_pnl=total_pnl, sharpe=sharpe,
        max_drawdown=max_drawdown, num_trades=num_trades, passed=passed, reason=reason,
        trade_pnls=trade_pnls,
    )
