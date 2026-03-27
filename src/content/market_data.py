"""Fetch market data from Binance public API."""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger("bsq.content")

TICKER_24H = "https://api.binance.com/api/v3/ticker/24hr"


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
