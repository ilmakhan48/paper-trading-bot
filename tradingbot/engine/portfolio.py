
class InsufficientFundsError(Exception):
    pass


class InsufficientPositionError(Exception):
    pass


class Portfolio:
    def __init__(self, cash: float):
        self.cash = cash
        self.positions: dict[str, dict] = {}
        self._open_fees: dict[str, float] = {}

    def equity(self, current_prices: dict[str, float]) -> float:
        """Mark open positions to current_prices; fall back to a held
        position's average entry price if this cycle's price fetch for that
        symbol failed and it's simply missing from current_prices. This keeps
        equity reporting honest (never raises) instead of taking down a
        caller that only has partial price data for a cycle."""
        total = self.cash
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol, pos["avg_price"])
            total += pos["qty"] * price
        return total

    def apply_buy(self, symbol: str, qty: float, price: float, fee: float):
        cost = qty * price
        if cost + fee > self.cash:
            raise InsufficientFundsError(
                f"Need {cost + fee:.2f} but only have {self.cash:.2f}"
            )
        self.cash -= (cost + fee)
        self.positions[symbol] = {"qty": qty, "avg_price": price}
        self._open_fees[symbol] = fee

    def apply_sell(self, symbol: str, qty: float, price: float, fee: float) -> float:
        position = self.positions.get(symbol)
        if position is None or position["qty"] < qty:
            raise InsufficientPositionError(f"No sufficient open position in {symbol}")
        proceeds = qty * price
        self.cash += proceeds - fee
        open_fee = self._open_fees.pop(symbol, 0.0)
        cost_basis = position["avg_price"] * qty
        pnl = proceeds - fee - cost_basis - open_fee
        del self.positions[symbol]
        return pnl
