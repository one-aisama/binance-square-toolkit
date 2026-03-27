"""Tests for browser_actions helper functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.session.browser_actions import _type_with_hashtag_handling


@pytest.fixture
def mock_page():
    page = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.press = AsyncMock()
    return page


@pytest.mark.asyncio
async def test_plain_text_no_tags(mock_page):
    await _type_with_hashtag_handling(mock_page, "Hello world")
    mock_page.keyboard.type.assert_called_once_with("Hello world", delay=60)
    mock_page.keyboard.press.assert_not_called()


@pytest.mark.asyncio
async def test_hashtag_triggers_escape(mock_page):
    await _type_with_hashtag_handling(mock_page, "Buy #BTC now")
    assert mock_page.keyboard.press.call_count == 1
    mock_page.keyboard.press.assert_called_with("Escape")


@pytest.mark.asyncio
async def test_cashtag_triggers_escape(mock_page):
    await _type_with_hashtag_handling(mock_page, "Buy $BTC now")
    assert mock_page.keyboard.press.call_count == 1
    mock_page.keyboard.press.assert_called_with("Escape")


@pytest.mark.asyncio
async def test_mixed_tags(mock_page):
    await _type_with_hashtag_handling(mock_page, "$BTC is pumping #crypto")
    assert mock_page.keyboard.press.call_count == 2


@pytest.mark.asyncio
async def test_consecutive_tags(mock_page):
    await _type_with_hashtag_handling(mock_page, "#BTC $ETH #SOL")
    assert mock_page.keyboard.press.call_count == 3


@pytest.mark.asyncio
async def test_tag_at_end(mock_page):
    await _type_with_hashtag_handling(mock_page, "Moon $BTC")
    assert mock_page.keyboard.press.call_count == 1
