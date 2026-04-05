import pytest

from src.content.validator import validate_post


def test_validate_post_blocks_consecutive_same_coin_ta_posts():
    recent_posts = [
        "$BTC still looks weak here\n\ndaily RSI is fading, MACD is still negative and 65.5K support is getting tested again. #BTC #Bitcoin"
    ]
    candidate = (
        "$BTC keeps flirting with 65.5K and people still want a clean answer.\n\n"
        "daily RSI is 41, MACD still ugly, and support keeps getting stress tested. #BTC #Bitcoin"
    )

    result = validate_post(candidate, recent_posts=recent_posts)

    assert result.valid is False
    assert any("same topic pattern" in error for error in result.errors)


def test_validate_post_allows_different_angle_after_btc_ta_post():
    recent_posts = [
        "$BTC still looks weak here\n\ndaily RSI is fading, MACD is still negative and 65.5K support is getting tested again. #BTC #Bitcoin"
    ]
    candidate = (
        "$BTC regulation story is getting more interesting.\n\n"
        "the real question now is how fragmented rules reshape global liquidity. #BTC #CryptoNews"
    )

    result = validate_post(candidate, recent_posts=recent_posts)

    assert result.valid is True
