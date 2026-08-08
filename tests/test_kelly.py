from tradingbot.sizing.kelly import kelly_fraction, fractional_kelly, position_size


def test_kelly_fraction_standard_formula():
    # p=0.6, b=1.5 (win pays 1.5x risk) -> f* = (b*p - q) / b = (1.5*0.6 - 0.4)/1.5
    f = kelly_fraction(win_rate=0.6, payoff_ratio=1.5)
    expected = (1.5 * 0.6 - 0.4) / 1.5
    assert abs(f - expected) < 1e-9


def test_kelly_fraction_clamped_to_zero_when_negative_edge():
    f = kelly_fraction(win_rate=0.3, payoff_ratio=1.0)
    assert f == 0.0


def test_kelly_fraction_clamped_to_one():
    f = kelly_fraction(win_rate=0.99, payoff_ratio=100.0)
    assert f <= 1.0


def test_fractional_kelly_applies_safety_fraction():
    full = kelly_fraction(win_rate=0.6, payoff_ratio=1.5)
    half = fractional_kelly(win_rate=0.6, payoff_ratio=1.5, fraction=0.5)
    assert abs(half - full * 0.5) < 1e-9


def test_position_size_never_exceeds_equity():
    size = position_size(equity=10000.0, win_rate=0.9, payoff_ratio=10.0, fraction=0.5)
    assert size <= 10000.0


def test_position_size_zero_when_no_edge():
    size = position_size(equity=10000.0, win_rate=0.2, payoff_ratio=1.0, fraction=0.5)
    assert size == 0.0
