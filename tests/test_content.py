"""Tests for content engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.content.generator import ContentGenerator
from src.content.market_data import get_trending_coins


# ---- Trending coins tests ----

COINGECKO_RESPONSE = [
    {
        "symbol": "btc", "name": "Bitcoin", "current_price": 95000.0,
        "price_change_percentage_24h": 2.5, "market_cap": 1_800_000_000_000,
        "total_volume": 30_000_000_000,
    },
    {
        "symbol": "eth", "name": "Ethereum", "current_price": 3500.0,
        "price_change_percentage_24h": -1.2, "market_cap": 420_000_000_000,
        "total_volume": 15_000_000_000,
    },
]


async def test_get_trending_coins_returns_list():
    mock_resp = MagicMock()
    mock_resp.json.return_value = COINGECKO_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("src.content.market_data.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await get_trending_coins(limit=2)

    assert len(result) == 2
    assert result[0]["symbol"] == "BTC"
    assert result[0]["rank"] == 1
    assert result[0]["price"] == 95000.0
    assert result[0]["change_24h"] == 2.5
    assert result[1]["symbol"] == "ETH"
    assert result[1]["change_24h"] == -1.2


async def test_get_trending_coins_null_change():
    """Coins with missing change_24h should return 0.0, not None."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{
        "symbol": "new", "name": "NewCoin", "current_price": 1.0,
        "price_change_percentage_24h": None, "market_cap": 1_000_000,
        "total_volume": 500_000,
    }]
    mock_resp.raise_for_status = MagicMock()

    with patch("src.content.market_data.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await get_trending_coins(limit=1)

    assert result[0]["change_24h"] == 0.0


# ---- Generator tests ----

def test_build_system_prompt():
    gen = ContentGenerator("anthropic", "test-model", "fake-key")
    prompt = gen._build_system_prompt("analytical, data-heavy", ["defi", "yield"])
    assert "analytical" in prompt
    assert "defi" in prompt
    assert "Never use typical AI writing style" in prompt
    assert "let's dive into" in prompt  # Bad example present
    assert "GOOD examples" in prompt
    assert "$CASHTAGS" in prompt


def test_build_user_prompt_with_market_data():
    gen = ContentGenerator("anthropic", "test-model", "fake-key")
    topic = {"name": "bitcoin", "hashtags": ["bitcoin", "btc"], "coins": ["BTC"]}
    market = {"BTC": {"price": 65000.0, "change_24h": 2.5, "volume": 1000000}}
    prompt = gen._build_user_prompt(topic, market)
    assert "bitcoin" in prompt
    assert "$BTC" in prompt
    assert "65,000" in prompt
    assert "+2.5%" in prompt


def test_build_user_prompt_empty():
    gen = ContentGenerator("anthropic", "test-model", "fake-key")
    prompt = gen._build_user_prompt({}, {})
    assert "crypto" in prompt

