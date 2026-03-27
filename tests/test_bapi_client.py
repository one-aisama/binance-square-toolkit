"""Tests for BapiClient."""

import pytest
import httpx
import time
from unittest.mock import AsyncMock, patch, MagicMock

from src.db.database import init_db
from src.session.credential_store import CredentialStore
from src.bapi.client import BapiClient, BapiCredentialError, BapiRequestError


@pytest.fixture
async def setup(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    store = CredentialStore(db_path)
    await store.save(
        "test_account",
        {"p20t": "token123", "csrftoken": "csrf_cookie"},
        {"csrftoken": "csrf_header", "bnc-uuid": "uuid-1", "user-agent": "TestUA"},
    )
    client = BapiClient(
        account_id="test_account",
        credential_store=store,
        base_url="https://www.binance.com",
        rate_limit_rpm=6000,  # High limit for fast tests
        retry_attempts=2,
        retry_backoff=0.01,
    )
    return client, store


def _mock_response(status_code: int, json_data: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "http://test"),
    )


async def test_get_injects_credentials(setup):
    client, _ = setup
    mock_resp = _mock_response(200, {"code": "000000", "data": {"list": []}})

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp) as mock_get:
        result = await client.get("/test/path", {"key": "val"})

    assert result["code"] == "000000"
    call_kwargs = mock_get.call_args
    headers = call_kwargs.kwargs.get("headers", {})
    assert "csrf_header" in headers.get("csrftoken", "")
    assert "cookie" in headers


async def test_post_sends_json(setup):
    client, _ = setup
    mock_resp = _mock_response(200, {"code": "000000", "data": {}})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        result = await client.post("/test/path", {"key": "val"})

    assert result["code"] == "000000"
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs.get("json") == {"key": "val"}


async def test_retry_on_500(setup):
    client, _ = setup
    fail_resp = _mock_response(500, {"error": "internal"})
    ok_resp = _mock_response(200, {"code": "000000", "data": {}})
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return fail_resp if call_count == 1 else ok_resp

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=side_effect):
        result = await client.get("/test")

    assert result["code"] == "000000"
    assert call_count == 2


async def test_invalidate_on_401(setup):
    client, store = setup
    mock_resp = _mock_response(401, {"code": "401"})

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(BapiCredentialError, match="expired"):
            await client.get("/test")

    assert await store.is_valid("test_account") is False


async def test_no_credentials_raises(setup):
    client, _ = setup
    client._account_id = "nonexistent"

    with pytest.raises(BapiCredentialError, match="No credentials"):
        await client.get("/test")


async def test_get_feed_recommend(setup):
    client, _ = setup
    mock_resp = _mock_response(200, {
        "code": "000000",
        "data": {"list": [{"id": "1"}, {"id": "2"}]},
    })
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.get_feed_recommend(page=1)
    assert len(result) == 2


async def test_get_top_articles(setup):
    client, _ = setup
    mock_resp = _mock_response(200, {
        "code": "000000",
        "data": {"list": [{"id": "a1"}]},
    })
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.get_top_articles(page=1)
    assert len(result) == 1


async def test_get_fear_greed(setup):
    client, _ = setup
    mock_resp = _mock_response(200, {
        "code": "000000",
        "data": {"fearGreedIndex": 65, "coins": ["BTC"]},
    })
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await client.get_fear_greed()
    assert result["fearGreedIndex"] == 65
