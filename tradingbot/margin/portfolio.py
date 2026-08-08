# tradingbot/margin/portfolio.py
from dataclasses import dataclass

# Binance tier-1 MMR, BTCUSDT/ETHUSDT/SOLUSDT under $50,000 notional.
# DISCLOSED ASSUMPTION, not independently confirmed: Binance's official leverage/margin
# tier page (https://www.binance.com/en/futures/trading-rules/perpetual/leverage-margin)
# renders its tier table via JavaScript and returned "No Data" placeholders when fetched
# during this task's verification step (2026-07-05); linked FAQ/announcement pages also
# did not expose the concrete BTCUSDT tier-1 percentage. Re-verify against a live Binance
# session or API before relying on this value for real trading.
MAINTENANCE_MARGIN_RATE = 0.004


class InsufficientMarginError(Exception):
    pass


class PositionAlreadyClosedError(Exception):
    pass


class PositionAlreadyOpenError(Exception):
    pass


def liquidation_price(entry_price: float, leverage: int, side: str,
                       mmr: float = MAINTENANCE_MARGIN_RATE) -> float:
    if side == "long":
        return entry_price * (1 - 1 / leverage + mmr)
    elif side == "short":
        return entry_price * (1 + 1 / leverage - mmr)
    else:
        raise ValueError(f"side must be 'long' or 'short', got {side!r}")


@dataclass
class MarginPosition:
    symbol: str
    side: str
    qty: float
    entry_price: float
    leverage: int
    margin: float
    liquidation_price: float
    funding_paid: float = 0.0


class MarginPortfolio:
    def __init__(self, cash: float):
        self.cash = cash
        self.positions: dict[str, MarginPosition] = {}

    def open_position(self, symbol: str, side: str, qty: float,
                       entry_price: float, leverage: int) -> MarginPosition:
        if symbol in self.positions:
            raise PositionAlreadyOpenError(
                f"Position already open for {symbol}; close it before opening a new one"
            )
        notional = qty * entry_price
        margin = notional / leverage
        if margin > self.cash:
            raise InsufficientMarginError(
                f"Need {margin:.2f} margin but only have {self.cash:.2f}"
            )
        liq_price = liquidation_price(entry_price, leverage, side)
        position = MarginPosition(
            symbol=symbol, side=side, qty=qty, entry_price=entry_price,
            leverage=leverage, margin=margin, liquidation_price=liq_price,
        )
        self.cash -= margin
        self.positions[symbol] = position
        return position

    def apply_funding(self, symbol: str, funding_rate: float, mark_price: float) -> float:
        position = self.positions[symbol]
        notional = position.qty * mark_price
        if position.side == "long":
            payment = -notional * funding_rate
        else:
            payment = notional * funding_rate
        self.cash += payment
        position.funding_paid += payment
        return payment

    def close_position(self, symbol: str, close_price: float) -> float:
        position = self.positions.get(symbol)
        if position is None:
            raise PositionAlreadyClosedError(f"No open position for {symbol}")
        if position.side == "long":
            pnl = position.qty * (close_price - position.entry_price)
        else:
            pnl = position.qty * (position.entry_price - close_price)
        self.cash += position.margin + pnl
        del self.positions[symbol]
        return pnl
