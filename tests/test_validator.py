"""Tests for credential validator with mocked httpx."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from src.session.validator import validate_credentials


def _make_response(status_code: int, json_data: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("POST", "http://test"),
    )


VALID_COOKIES = {"p20t": "abc", "csrftoken": "xyz"}
VALID_HEADERS = {"csrftoken": "xyz", "bnc-uuid": "uuid-1", "user-agent": "Mozilla/5.0"}


async def test_valid_credentials():
    mock_resp = _make_response(200, {"code": "000000", "success": True, "data": {}})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await validate_credentials(VALID_COOKIES, VALID_HEADERS)
    assert result is True


async def test_invalid_code():
    mock_resp = _make_response(200, {"code": "000002", "success": False, "message": "illegal parameter"})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await validate_credentials(VALID_COOKIES, VALID_HEADERS)
    assert result is False


async def test_unauthorized_401():
    mock_resp = _make_response(401, {"code": "401", "message": "unauthorized"})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await validate_credentials(VALID_COOKIES, VALID_HEADERS)
    assert result is False


async def test_redirect_302():
    mock_resp = httpx.Response(
        status_code=302,
        headers={"location": "/login"},
        request=httpx.Request("POST", "http://test"),
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await validate_credentials(VALID_COOKIES, VALID_HEADERS)
    assert result is False


async def test_network_error():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.ConnectError("failed")):
        result = await validate_credentials(VALID_COOKIES, VALID_HEADERS)
    assert result is False


async def test_timeout():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("timeout")):
        result = await validate_credentials(VALID_COOKIES, VALID_HEADERS)
    assert result is False


async def test_empty_cookies_and_headers():
    mock_resp = _make_response(200, {"code": "000000", "success": True})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await validate_credentials({}, {})
    assert result is True
