import pytest
import requests
from unittest.mock import patch, Mock
from tradingbot.margin.funding import get_mark_price, get_funding_rate, FundingFetchError


def test_get_mark_price_parses_response():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "symbol": "BTCUSDT", "markPrice": "62700.30000000",
        "indexPrice": "62728.07456522", "lastFundingRate": "0.00010000",
        "nextFundingTime": 1783267200000, "time": 1783254516000,
    }
    with patch("tradingbot.margin.funding.requests.get", return_value=fake_response) as mock_get:
        price = get_mark_price("BTCUSDT")
    assert price == 62700.30
    mock_get.assert_called_once_with(
        "https://fapi.binance.com/fapi/v1/premiumIndex",
        params={"symbol": "BTCUSDT"},
        timeout=10,
    )


def test_get_mark_price_raises_on_http_error():
    fake_response = Mock()
    fake_response.status_code = 500
    with patch("tradingbot.margin.funding.requests.get", return_value=fake_response):
        with pytest.raises(FundingFetchError):
            get_mark_price("BTCUSDT")


def test_get_funding_rate_parses_most_recent():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = [
        {"symbol": "BTCUSDT", "fundingTime": 1783238400001,
         "fundingRate": "0.00008873", "markPrice": "62997.87521014"}
    ]
    with patch("tradingbot.margin.funding.requests.get", return_value=fake_response) as mock_get:
        rate = get_funding_rate("BTCUSDT")
    assert rate == pytest.approx(0.00008873)
    mock_get.assert_called_once_with(
        "https://fapi.binance.com/fapi/v1/fundingRate",
        params={"symbol": "BTCUSDT", "limit": 1},
        timeout=10,
    )


def test_get_funding_rate_raises_on_http_error():
    fake_response = Mock()
    fake_response.status_code = 500
    with patch("tradingbot.margin.funding.requests.get", return_value=fake_response):
        with pytest.raises(FundingFetchError):
            get_funding_rate("BTCUSDT")


def test_get_mark_price_wraps_connection_error():
    with patch(
        "tradingbot.margin.funding.requests.get",
        side_effect=requests.exceptions.ConnectionError("boom"),
    ):
        with pytest.raises(FundingFetchError):
            get_mark_price("BTCUSDT")


def test_get_funding_rate_wraps_connection_error():
    with patch(
        "tradingbot.margin.funding.requests.get",
        side_effect=requests.exceptions.ConnectionError("boom"),
    ):
        with pytest.raises(FundingFetchError):
            get_funding_rate("BTCUSDT")


def test_get_funding_rate_raises_on_empty_rows():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = []
    with patch("tradingbot.margin.funding.requests.get", return_value=fake_response):
        with pytest.raises(FundingFetchError):
            get_funding_rate("BTCUSDT")


def test_get_mark_price_raises_on_malformed_json():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"unexpected": "shape"}
    with patch("tradingbot.margin.funding.requests.get", return_value=fake_response):
        with pytest.raises(FundingFetchError):
            get_mark_price("BTCUSDT")
