from tradingbot.margin.db import insert_position, add_funding, close_position as db_close_position
from tradingbot.margin.portfolio import MarginPortfolio


class MarginBroker:
    def __init__(self, portfolio: MarginPortfolio, conn):
        self.portfolio = portfolio
        self.conn = conn
        self._position_ids: dict[str, int] = {}

    def open_position(self, *, symbol, side, qty, entry_price, leverage, opened_at) -> int:
        position = self.portfolio.open_position(symbol, side, qty, entry_price, leverage)
        position_id = insert_position(
            self.conn, symbol=symbol, side=side, qty=qty, entry_price=entry_price,
            leverage=leverage, margin=position.margin,
            liquidation_price=position.liquidation_price, opened_at=opened_at,
        )
        self._position_ids[symbol] = position_id
        return position_id

    def apply_funding(self, symbol, funding_rate, mark_price) -> float:
        payment = self.portfolio.apply_funding(symbol, funding_rate, mark_price)
        add_funding(self.conn, self._position_ids[symbol], payment)
        return payment

    def close_position(self, symbol, close_price, closed_at) -> float:
        pnl = self.portfolio.close_position(symbol, close_price)
        position_id = self._position_ids.pop(symbol)
        db_close_position(
            self.conn, position_id, close_price=close_price, pnl=pnl,
            closed_at=closed_at, liquidated=False,
        )
        return pnl

    def check_liquidation(self, symbol, mark_price, closed_at) -> bool:
        position = self.portfolio.positions.get(symbol)
        if position is None:
            return False
        breached = (
            (position.side == "long" and mark_price <= position.liquidation_price)
            or (position.side == "short" and mark_price >= position.liquidation_price)
        )
        if not breached:
            return False
        pnl = self.portfolio.close_position(symbol, position.liquidation_price)
        position_id = self._position_ids.pop(symbol)
        db_close_position(
            self.conn, position_id, close_price=position.liquidation_price, pnl=pnl,
            closed_at=closed_at, liquidated=True,
        )
        return True
