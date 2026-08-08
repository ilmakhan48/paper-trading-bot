from tradingbot.engine.db import insert_trade, close_trade as db_close_trade
from tradingbot.engine.portfolio import Portfolio

TAKER_FEE_RATE = 0.001   # Binance spot taker fee, 0.1%
SLIPPAGE_RATE = 0.0005   # fixed unfavorable slippage model, 0.05%


class Broker:
    def __init__(self, portfolio: Portfolio, conn):
        self.portfolio = portfolio
        self.conn = conn
        self._open_symbol_for_trade: dict[int, str] = {}

    def _fill_price(self, side: str, market_price: float) -> float:
        if side == "buy":
            return market_price * (1 + SLIPPAGE_RATE)
        return market_price * (1 - SLIPPAGE_RATE)

    def open_trade(self, *, symbol, side, qty, market_price, strategy, opened_at) -> int:
        fill_price = self._fill_price(side, market_price)
        fee = fill_price * qty * TAKER_FEE_RATE
        if side == "buy":
            self.portfolio.apply_buy(symbol, qty, fill_price, fee)
        else:
            self.portfolio.apply_sell(symbol, qty, fill_price, fee)
        trade_id = insert_trade(
            self.conn, symbol=symbol, side=side, qty=qty, price=fill_price,
            fee=fee, slippage=abs(fill_price - market_price) * qty,
            strategy=strategy, opened_at=opened_at,
        )
        self._open_symbol_for_trade[trade_id] = symbol
        return trade_id

    def close_trade(self, trade_id: int, *, symbol, market_price, closed_at) -> float:
        position = self.portfolio.positions[symbol]
        qty = position["qty"]
        fill_price = self._fill_price("sell", market_price)
        fee = fill_price * qty * TAKER_FEE_RATE
        pnl = self.portfolio.apply_sell(symbol, qty, fill_price, fee)
        db_close_trade(
            self.conn, trade_id, close_price=fill_price, fee=fee,
            slippage=abs(fill_price - market_price) * qty, pnl=pnl, closed_at=closed_at,
        )
        return pnl
