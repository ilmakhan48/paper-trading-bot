from datetime import datetime, timezone

import requests

BASE_URL = "https://api.binance.com/api/v3"


class PriceFetchError(Exception):
    pass


def get_price(symbol: str) -> float:
    response = requests.get(
        f"{BASE_URL}/ticker/price",
        params={"symbol": symbol},
        timeout=10,
    )
    if response.status_code != 200:
        raise PriceFetchError(
            f"Binance price fetch failed for {symbol}: HTTP {response.status_code}"
        )
    data = response.json()
    return float(data["price"])


def get_klines(symbol: str, interval: str, limit: int) -> list[dict]:
    response = requests.get(
        f"{BASE_URL}/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=10,
    )
    if response.status_code != 200:
        raise PriceFetchError(
            f"Binance klines fetch failed for {symbol}: HTTP {response.status_code}"
        )
    rows = response.json()
    return [
        {
            "open_time": datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in rows
    ]
