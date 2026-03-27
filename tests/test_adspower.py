import pytest
import httpx
from unittest.mock import AsyncMock, patch
from src.session.adspower import AdsPowerClient, AdsPowerError


def _mock_response(json_data, status_code=200):
    """Create a mock httpx.Response."""
    resp = httpx.Response(status_code=status_code, json=json_data, request=httpx.Request("GET", "http://test"))
    return resp


@pytest.fixture
def client():
    return AdsPowerClient(
        base_url="http://localhost:50325",
        retry_attempts=2,
        retry_backoff=0.01,  # Fast retries for tests
    )


async def test_get_status_success(client):
    mock_resp = _mock_response({"code": 0, "msg": "success"})
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.get_status()
    assert result["code"] == 0


async def test_start_browser_returns_ws(client):
    mock_resp = _mock_response({
        "code": 0,
        "msg": "success",
        "data": {
            "ws": {"puppeteer": "ws://127.0.0.1:9222/devtools/browser/xxx"},
            "debug_port": "9222",
            "webdriver": "C:\\chromedriver.exe",
        },
    })
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.start_browser("profile_1")
    assert result["ws"] == "ws://127.0.0.1:9222/devtools/browser/xxx"
    assert result["debug_port"] == "9222"
    assert result["webdriver"] == "C:\\chromedriver.exe"


async def test_stop_browser_success(client):
    mock_resp = _mock_response({"code": 0, "msg": "success"})
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.stop_browser("profile_1")
    assert result["code"] == 0


async def test_retry_on_timeout(client):
    mock_success = _mock_response({"code": 0, "msg": "success"})
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.TimeoutException("timeout")
        return mock_success

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, side_effect=side_effect):
        result = await client.get_status()
    assert result["code"] == 0
    assert call_count == 2


async def test_retry_exhausted_raises(client):
    async def side_effect(*args, **kwargs):
        raise httpx.TimeoutException("timeout")

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, side_effect=side_effect):
        with pytest.raises(AdsPowerError, match="failed after 2 attempts"):
            await client.get_status()


async def test_api_error_code_raises(client):
    mock_resp = _mock_response({"code": -1, "msg": "profile not found"})
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(AdsPowerError, match="profile not found"):
            await client.start_browser("bad_id")
