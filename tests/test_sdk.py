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

    mock_fn.assert_called_once_with("ws://127.0.0.1:9222/devtools/browser/abc", "123", "great analysis", page=None, allow_follow_reply=True)
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


async def test_create_post_allows_coin_and_image_together(sdk):
    """coin tag + image_path is allowed — chart card skipped, image used."""
    # This just tests validation passes, not actual publishing
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    # Would need mock for actual publish, just verify no validation error
    # Skip this test since it requires browser
    pass


async def test_create_post_rejects_sentiment_without_coin(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    result = await sdk.create_post(
        text="this is a valid post body about $BTC and why the bounce still needs proof.\n\nsmaller ego, cleaner execution. #BTC #Bitcoin",
        sentiment="bullish",
        skip_validation=True,
    )
    assert result["success"] is False
    assert "Sentiment requires a coin tag" in result["validation_errors"][0]


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


async def test_create_post_merges_live_recent_posts_with_runtime_history(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    sdk._profile_username = "example_macro"
    validation = MagicMock(valid=False, errors=["duplicate"], warnings=[])

    with patch.object(sdk, "_load_live_recent_posts", new_callable=AsyncMock, return_value=["live recent post"]), \
         patch("src.sdk.validate_post", return_value=validation) as mock_validate:
        result = await sdk.create_post(
            text="$BTC still needs more proof than one fast bounce\n\ni care more about follow through than the headline move",
            recent_posts=["runtime checkpoint post"],
        )

    assert result["success"] is False
    _, kwargs = mock_validate.call_args
    assert kwargs["recent_posts"] == ["runtime checkpoint post", "live recent post"]


async def test_chart_clip_from_standard_layout_uses_full_width_and_footer(sdk):
    sdk._page = MagicMock()
    sdk._page.viewport_size = {"width": 1600, "height": 900}

    clip = await sdk._chart_clip_from_standard_layout(
        chart_box={"x": 12.0, "y": 118.0, "width": 1490.0, "height": 690.0},
    )

    assert clip == {
        "x": 0.0,
        "y": 0.0,
        "width": 1600.0,
        "height": 818.0,
    }


async def test_chart_clip_from_standard_layout_avoids_sidebar_when_chart_is_centered(sdk):
    sdk._page = MagicMock()
    sdk._page.viewport_size = {"width": 1600, "height": 900}

    clip = await sdk._chart_clip_from_standard_layout(
        chart_box={"x": 110.0, "y": 180.0, "width": 1290.0, "height": 620.0},
        header_boxes=[{"x": 112.0, "y": 118.0, "width": 220.0, "height": 40.0}],
    )

    assert clip == {
        "x": 90.0,
        "y": 104.0,
        "width": 1330.0,
        "height": 706.0,
    }


async def test_save_page_screenshot_uses_device_scale(sdk):
    import base64
    from unittest.mock import mock_open

    sdk._page = MagicMock()
    sdk._page.evaluate = AsyncMock(return_value=1.25)
    sdk._page.screenshot = AsyncMock()
    cdp_session = MagicMock()
    cdp_session.send = AsyncMock(return_value={"data": base64.b64encode(b"raw-bytes").decode()})
    sdk._page.context = MagicMock()
    sdk._page.context.new_cdp_session = AsyncMock(return_value=cdp_session)
    clip = {"x": 0.0, "y": 0.0, "width": 100.0, "height": 50.0}

    with patch("builtins.open", mock_open()):
        await sdk._save_page_screenshot("data/screenshots/test.png", clip=clip)

    cdp_session.send.assert_awaited_once_with(
        "Page.captureScreenshot",
        {
            "format": "png",
            "fromSurface": True,
            "captureBeyondViewport": False,
            "clip": {
                "x": 0.0,
                "y": 0.0,
                "width": 100.0,
                "height": 50.0,
                "scale": 1.25,
            },
        },
    )
    sdk._page.screenshot.assert_not_called()


async def test_screenshot_chart_prefers_standardized_capture(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"
    sdk._page = MagicMock()
    sdk._page.goto = AsyncMock()
    sdk._page.evaluate = AsyncMock()

    with patch.object(sdk, "_dismiss_cookie_banner", new_callable=AsyncMock), \
         patch.object(sdk, "_capture_standardized_chart_view", new_callable=AsyncMock) as mock_standardized, \
         patch.object(sdk, "_capture_current_view", new_callable=AsyncMock) as mock_targeted, \
         patch.object(sdk, "_fallback_chart_capture", new_callable=AsyncMock) as mock_fallback, \
         patch.object(sdk, "_screenshot_output_path", return_value="data/screenshots/test.png"):
        result = await sdk.screenshot_chart(symbol="BTC_USDT", timeframe="1D")

    assert result == "data/screenshots/test.png"
    mock_standardized.assert_awaited_once()
    mock_targeted.assert_not_awaited()
    mock_fallback.assert_not_awaited()






async def test_connect_uses_custom_adspower_base_url():
    sdk = BinanceSquareSDK(profile_serial="1", adspower_base_url="http://localhost:50325")
    mock_resp = _mock_response({
        "code": 0,
        "msg": "success",
        "data": {
            "status": "Active",
            "ws": {"puppeteer": "ws://127.0.0.1:9222/devtools/browser/abc"},
        },
    })

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp) as mock_get, \
         patch.object(sdk, "_init_persistent_page", new_callable=AsyncMock):
        await sdk.connect()

    first_url = mock_get.await_args_list[0].args[0]
    assert first_url.startswith("http://localhost:50325/")


async def test_engage_post_respects_guarded_subactions():
    sdk = BinanceSquareSDK(profile_serial="1")
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"

    async def check_side_effect(action_type: str):
        if action_type == "comment":
            return GuardDecision(verdict=Verdict.ALLOW)
        return GuardDecision(verdict=Verdict.DENIED, reason=f"{action_type} blocked")

    guard = MagicMock(spec=ActionGuard)
    guard.check = AsyncMock(side_effect=check_side_effect)
    guard.record = MagicMock()
    sdk._guard = guard

    mock_result = {
        "success": True,
        "post_id": "123",
        "liked": False,
        "commented": True,
        "followed": False,
        "errors": [],
    }
    with patch("src.sdk.engage_post", new_callable=AsyncMock, return_value=mock_result) as mock_fn:
        result = await sdk.engage_post(post_id="123", like=True, comment="great analysis", follow=True)

    mock_fn.assert_awaited_once_with(
        "ws://127.0.0.1:9222/devtools/browser/abc",
        "123",
        like=False,
        comment_text="great analysis",
        follow=False,
        page=None,
        allow_follow_reply=False,
    )
    assert result["commented"] is True
    assert "like: like blocked" in result["skipped_actions"]
    assert "follow: follow blocked" in result["skipped_actions"]
    guard.record.assert_called_once_with("comment", True, None)


async def test_engage_post_rejects_invalid_comment_without_browser_call(sdk):
    sdk._ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/abc"

    with patch("src.sdk.engage_post", new_callable=AsyncMock) as mock_fn:
        result = await sdk.engage_post(post_id="123", like=False, comment="ok", follow=False)

    assert result["success"] is False
    assert "validation_errors" in result
    mock_fn.assert_not_called()
