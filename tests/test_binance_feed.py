import pytest
from unittest.mock import patch, Mock
from tradingbot.data.binance_feed import get_price, get_klines, PriceFetchError


def test_get_price_parses_response():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"symbol": "BTCUSDT", "price": "62857.71000000"}
    with patch("tradingbot.data.binance_feed.requests.get", return_value=fake_response) as mock_get:
        price = get_price("BTCUSDT")
    assert price == 62857.71
    mock_get.assert_called_once_with(
        "https://api.binance.com/api/v3/ticker/price",
        params={"symbol": "BTCUSDT"},
        timeout=10,
    )


def test_get_price_raises_on_http_error():
    fake_response = Mock()
    fake_response.status_code = 500
    with patch("tradingbot.data.binance_feed.requests.get", return_value=fake_response):
        with pytest.raises(PriceFetchError):
            get_price("BTCUSDT")


def test_get_klines_parses_rows():
    raw_row = [
        1783238400000, "63020.21000000", "63104.00000000",
        "62900.00000000", "62915.00000000", "337.45972000",
        1783241999999, "21249003.10070990", 54807,
        "146.25020000", "9210215.26308660", "0",
    ]
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = [raw_row]
    with patch("tradingbot.data.binance_feed.requests.get", return_value=fake_response):
        klines = get_klines("BTCUSDT", "1h", 1)
    assert len(klines) == 1
    row = klines[0]
    assert row["open"] == 63020.21
    assert row["close"] == 62915.00
    assert row["high"] == 63104.00
    assert row["low"] == 62900.00
