def kelly_fraction(win_rate: float, payoff_ratio: float) -> float:
    p = win_rate
    q = 1 - win_rate
    b = payoff_ratio
    if b <= 0:
        return 0.0
    f = (b * p - q) / b
    return max(0.0, min(f, 1.0))


def fractional_kelly(win_rate: float, payoff_ratio: float, fraction: float = 0.5) -> float:
    return kelly_fraction(win_rate, payoff_ratio) * fraction


def position_size(equity: float, win_rate: float, payoff_ratio: float, fraction: float = 0.5) -> float:
    f = fractional_kelly(win_rate, payoff_ratio, fraction)
    return equity * f
