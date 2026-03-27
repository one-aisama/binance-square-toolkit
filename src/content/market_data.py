"""Fetch market data from Binance and CoinGecko public APIs."""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger("bsq.content")

TICKER_24H = "https://api.binance.com/api/v3/ticker/24hr"
COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"


async def get_market_data(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch current prices and 24h change for given symbols.

    Args:
        symbols: List of coin symbols like ["BTC", "ETH", "BNB"]

    Returns:
        Dict mapping symbol to price data: {price, change_24h, volume}
    """
    results = {}
    async with httpx.AsyncClient(timeout=15.0) as client:
        tasks = [_fetch_ticker(client, symbol) for symbol in symbols]
        fetched = await asyncio.gather(*tasks, return_exceptions=True)
        for symbol, data in zip(symbols, fetched):
            if isinstance(data, dict):
                results[symbol] = data
            else:
                logger.warning(f"Failed to fetch market data for {symbol}: {data}")
    return results


async def _fetch_ticker(client: httpx.AsyncClient, symbol: str) -> dict[str, Any]:
    """Fetch 24h ticker for a single symbol."""
    resp = await client.get(TICKER_24H, params={"symbol": f"{symbol}USDT"})
    resp.raise_for_status()
    data = resp.json()
    return {
        "price": float(data["lastPrice"]),
        "change_24h": float(data["priceChangePercent"]),
        "volume": float(data["volume"]),
    }


async def get_trending_coins(limit: int = 10) -> list[dict[str, Any]]:
    """Get top coins by market cap with 24h change from CoinGecko.

    No API key required.

    Args:
        limit: Number of coins to return. Default: 10

    Returns:
        List of dicts: [{rank, symbol, name, price, change_24h, market_cap, volume_24h}]
        Sorted by market cap rank (BTC first).
    """
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(COINGECKO_MARKETS, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = []
    for i, coin in enumerate(data, start=1):
        results.append({
            "rank": i,
            "symbol": coin["symbol"].upper(),
            "name": coin["name"],
            "price": coin["current_price"],
            "change_24h": coin.get("price_change_percentage_24h") or 0.0,
            "market_cap": coin["market_cap"],
            "volume_24h": coin["total_volume"],
        })
    logger.info(f"Fetched {len(results)} trending coins from CoinGecko")
    return results
