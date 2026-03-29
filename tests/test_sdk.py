"""Tests for BinanceSquareSDK."""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from src.sdk import BinanceSquareSDK, SDKError
from src.runtime.guard import ActionGuard, Verdict, GuardDecision


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
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp), \
         patch.object(sdk, "_init_persistent_page", new_callable=AsyncMock):
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

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=side_effect), \
         patch.object(sdk, "_init_persistent_page", new_callable=AsyncMock):
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

    mock_fn.assert_called_once_with("ws://127.0.0.1:9222/devtools/browser/abc", count=10, tab="trending", page=None)
    assert result == mock_posts


# ---- comment_on_post() ----


async def test_comment_on_post_calls_browser_action(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    mock_result = {"success": True, "post_id": "123", "followed": False}

    with patch("src.sdk.comment_on_post", new_callable=AsyncMock, return_value=mock_result) as mock_fn:
        result = await sdk.comment_on_post(post_id="123", text="great analysis")

    mock_fn.assert_called_once_with("ws://127.0.0.1:9222/devtools/browser/abc", "123", "great analysis", page=None)
    assert result["success"] is True


# ---- create_post() ----


async def test_create_post_calls_browser_action(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    mock_result = {"success": True, "post_id": "456", "response": {}}

    post_text = (
        "$BTC looking strong on the daily chart. RSI at 62, MACD crossing up.\n\n"
        "watching 72k resistance. if it breaks with volume, could push to ATH. #Bitcoin"
    )
    with patch("src.sdk.create_post", new_callable=AsyncMock, return_value=mock_result) as mock_fn:
        result = await sdk.create_post(text=post_text, coin="BTC", sentiment="bullish")

    mock_fn.assert_called_once_with(
        "ws://127.0.0.1:9222/devtools/browser/abc",
        post_text,
        coin="BTC",
        sentiment="bullish",
        image_path=None,
        page=None,
    )
    assert result["success"] is True


async def test_create_post_validation_rejects_short_text(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    result = await sdk.create_post(text="$BTC up", coin="BTC")
    assert result["success"] is False
    assert "validation_errors" in result


async def test_create_post_skip_validation(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    mock_result = {"success": True, "post_id": "789", "response": {}}

    with patch("src.sdk.create_post", new_callable=AsyncMock, return_value=mock_result) as mock_fn:
        result = await sdk.create_post(text="short", skip_validation=True)
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


# ---- Guard integration ----


def _make_mock_guard(verdict: Verdict, **kwargs) -> MagicMock:
    """Create a mock ActionGuard returning the given verdict."""
    guard = MagicMock(spec=ActionGuard)
    decision = GuardDecision(verdict=verdict, **kwargs)
    guard.check = AsyncMock(return_value=decision)
    guard.record = MagicMock()
    return guard


@pytest.fixture
def sdk_with_guard_allow():
    guard = _make_mock_guard(Verdict.ALLOW)
    sdk = BinanceSquareSDK(profile_serial="1")
    sdk._guard = guard
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    return sdk


@pytest.fixture
def sdk_with_guard_denied():
    guard = _make_mock_guard(Verdict.DENIED, reason="Daily limit reached")
    sdk = BinanceSquareSDK(profile_serial="1")
    sdk._guard = guard
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    return sdk


@pytest.fixture
def sdk_with_guard_session_over():
    guard = _make_mock_guard(Verdict.SESSION_OVER, reason="Too many failures")
    sdk = BinanceSquareSDK(profile_serial="1")
    sdk._guard = guard
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    return sdk


def test_guard_is_none_before_connect():
    sdk = BinanceSquareSDK(profile_serial="1")
    assert sdk._guard is None


async def test_check_guard_allows_when_no_guard(sdk):
    allowed, reason = await sdk._check_guard("like")
    assert allowed is True


async def test_check_guard_allows_when_verdict_allow(sdk_with_guard_allow):
    allowed, reason = await sdk_with_guard_allow._check_guard("like")
    assert allowed is True


async def test_check_guard_denies_when_verdict_denied(sdk_with_guard_denied):
    allowed, reason = await sdk_with_guard_denied._check_guard("like")
    assert allowed is False
    assert "Daily limit" in reason


async def test_check_guard_denies_when_session_over(sdk_with_guard_session_over):
    allowed, reason = await sdk_with_guard_session_over._check_guard("like")
    assert allowed is False
    assert "Too many failures" in reason


async def test_like_post_denied_by_guard(sdk_with_guard_denied):
    result = await sdk_with_guard_denied.like_post(post_id="123")
    assert result["success"] is False
    assert "Guard denied" in result["error"]


async def test_comment_denied_by_guard(sdk_with_guard_denied):
    result = await sdk_with_guard_denied.comment_on_post(post_id="123", text="test")
    assert result["success"] is False
    assert "Guard denied" in result["error"]


async def test_create_post_denied_by_guard(sdk_with_guard_denied):
    result = await sdk_with_guard_denied.create_post(text="test", skip_validation=True)
    assert result["success"] is False
    assert "Guard denied" in result["error"]


async def test_create_article_denied_by_guard(sdk_with_guard_denied):
    result = await sdk_with_guard_denied.create_article(
        title="Test", body="Test body", skip_validation=True,
    )
    assert result["success"] is False
    assert "Guard denied" in result["error"]


async def test_quote_repost_denied_by_guard(sdk_with_guard_denied):
    result = await sdk_with_guard_denied.quote_repost(post_id="123", skip_validation=True)
    assert result["success"] is False
    assert "Guard denied" in result["error"]


async def test_follow_user_denied_by_guard(sdk_with_guard_denied):
    result = await sdk_with_guard_denied.follow_user(post_id="123")
    assert result["success"] is False
    assert "Guard denied" in result["error"]


async def test_comment_records_success_in_guard(sdk_with_guard_allow):
    mock_result = {"success": True, "post_id": "123", "followed": False}
    with patch("src.sdk.comment_on_post", new_callable=AsyncMock, return_value=mock_result):
        await sdk_with_guard_allow.comment_on_post(post_id="123", text="great analysis")
    sdk_with_guard_allow._guard.record.assert_called_once_with("comment", True, None)


async def test_follow_records_success_in_guard(sdk_with_guard_allow):
    mock_result = {"success": True, "post_id": "123", "action": "followed"}
    with patch("src.sdk.follow_author", new_callable=AsyncMock, return_value=mock_result):
        await sdk_with_guard_allow.follow_user(post_id="123")
    sdk_with_guard_allow._guard.record.assert_called_once_with("follow", True, None)


async def test_record_guard_noop_without_guard(sdk):
    sdk._record_guard("like", success=True)  # should not raise
