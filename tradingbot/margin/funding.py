import requests

BASE_URL = "https://fapi.binance.com/fapi/v1"


class FundingFetchError(Exception):
    pass


def get_mark_price(symbol: str) -> float:
    try:
        response = requests.get(
            f"{BASE_URL}/premiumIndex",
            params={"symbol": symbol},
            timeout=10,
        )
    except requests.exceptions.RequestException as exc:
        raise FundingFetchError(
            f"Binance mark price fetch failed for {symbol}: {exc}"
        ) from exc
    if response.status_code != 200:
        raise FundingFetchError(
            f"Binance mark price fetch failed for {symbol}: HTTP {response.status_code}"
        )
    try:
        data = response.json()
        return float(data["markPrice"])
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise FundingFetchError(
            f"Binance mark price response malformed for {symbol}: {exc}"
        ) from exc


def get_funding_rate(symbol: str) -> float:
    try:
        response = requests.get(
            f"{BASE_URL}/fundingRate",
            params={"symbol": symbol, "limit": 1},
            timeout=10,
        )
    except requests.exceptions.RequestException as exc:
        raise FundingFetchError(
            f"Binance funding rate fetch failed for {symbol}: {exc}"
        ) from exc
    if response.status_code != 200:
        raise FundingFetchError(
            f"Binance funding rate fetch failed for {symbol}: HTTP {response.status_code}"
        )
    try:
        rows = response.json()
        return float(rows[0]["fundingRate"])
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise FundingFetchError(
            f"Binance funding rate response malformed for {symbol}: {exc}"
        ) from exc
