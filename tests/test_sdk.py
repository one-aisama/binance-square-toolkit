"""Tests for BinanceSquareSDK."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch

from src.sdk import BinanceSquareSDK, SDKError


def _mock_response(json_data, status_code=200):
    """Create a mock httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "http://test"),
    )


@pytest.fixture
def sdk():
    return BinanceSquareSDK(profile_serial="1")


# ---- Constructor ----


def test_constructor_sets_profile_serial(sdk):
    assert sdk._serial == "1"


def test_constructor_ws_endpoint_is_none(sdk):
    assert sdk._ws_endpoint is None


# ---- connect() ----


async def test_connect_active_profile_sets_ws_endpoint(sdk):
    mock_resp = _mock_response({
        "code": 0,
        "msg": "success",
        "data": {
            "status": "Active",
            "ws": {"puppeteer": "ws://127.0.0.1:9222/devtools/browser/abc"},
        },
    })
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        await sdk.connect()

    assert sdk._ws_endpoint == "ws://127.0.0.1:9222/devtools/browser/abc"


async def test_connect_inactive_profile_starts_browser(sdk):
    inactive_resp = _mock_response({
        "code": 0,
        "msg": "success",
        "data": {"status": "Inactive"},
    })
    start_resp = _mock_response({
        "code": 0,
        "msg": "success",
        "data": {
            "ws": {"puppeteer": "ws://127.0.0.1:9333/devtools/browser/def"},
        },
    })
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return inactive_resp if call_count == 1 else start_resp

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=side_effect):
        await sdk.connect()

    assert sdk._ws_endpoint == "ws://127.0.0.1:9333/devtools/browser/def"


async def test_connect_adspower_error_raises_sdk_error(sdk):
    inactive_resp = _mock_response({
        "code": 0,
        "msg": "success",
        "data": {"status": "Inactive"},
    })
    error_resp = _mock_response({
        "code": -1,
        "msg": "profile not found",
    })
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return inactive_resp if call_count == 1 else error_resp

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=side_effect):
        with pytest.raises(SDKError, match="Failed to start profile"):
            await sdk.connect()


# ---- disconnect() ----


async def test_disconnect_clears_ws_endpoint(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    await sdk.disconnect()
    assert sdk._ws_endpoint is None


# ---- _require_connection() ----


def test_require_connection_raises_when_not_connected(sdk):
    with pytest.raises(SDKError, match="Not connected"):
        sdk._require_connection()


def test_require_connection_returns_ws_when_connected(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    result = sdk._require_connection()
    assert result == "ws://127.0.0.1:9222/devtools/browser/abc"


# ---- get_feed_posts() ----


async def test_get_feed_posts_calls_collect_with_ws_endpoint(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    mock_posts = [{"post_id": "1", "text": "hello"}]

    with patch("src.sdk.collect_feed_posts", new_callable=AsyncMock, return_value=mock_posts) as mock_fn:
        result = await sdk.get_feed_posts(count=10, tab="trending")

    mock_fn.assert_called_once_with("ws://127.0.0.1:9222/devtools/browser/abc", count=10, tab="trending")
    assert result == mock_posts


# ---- comment_on_post() ----


async def test_comment_on_post_calls_browser_action(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    mock_result = {"success": True, "post_id": "123", "followed": False}

    with patch("src.sdk.comment_on_post", new_callable=AsyncMock, return_value=mock_result) as mock_fn:
        result = await sdk.comment_on_post(post_id="123", text="great analysis")

    mock_fn.assert_called_once_with("ws://127.0.0.1:9222/devtools/browser/abc", "123", "great analysis")
    assert result["success"] is True


# ---- create_post() ----


async def test_create_post_calls_browser_action(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    mock_result = {"success": True, "post_id": "456", "response": {}}

    with patch("src.sdk.create_post", new_callable=AsyncMock, return_value=mock_result) as mock_fn:
        result = await sdk.create_post(text="$BTC looking strong", coin="BTC", sentiment="bullish")

    mock_fn.assert_called_once_with(
        "ws://127.0.0.1:9222/devtools/browser/abc",
        "$BTC looking strong",
        coin="BTC",
        sentiment="bullish",
        image_path=None,
    )
    assert result["success"] is True


# ---- get_market_data() ----


async def test_get_market_data_calls_content_module(sdk):
    mock_data = {
        "BTC": {"price": 67000, "change_24h": 2.5, "volume": 1_000_000},
        "ETH": {"price": 3500, "change_24h": -1.2, "volume": 500_000},
    }

    with patch("src.sdk.get_market_data", new_callable=AsyncMock, return_value=mock_data) as mock_fn:
        result = await sdk.get_market_data(symbols=["BTC", "ETH"])

    mock_fn.assert_called_once_with(["BTC", "ETH"])
    assert "BTC" in result
    assert "ETH" in result
