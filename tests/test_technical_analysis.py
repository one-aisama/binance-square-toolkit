"""Tests for technical analysis module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.content.technical_analysis import (
    get_ta_summary, _rsi, _macd, _sma, _ema, _support_resistance, TAError,
)


# ---- Generate synthetic candle data ----

def make_closes(n: int = 200, start: float = 50000.0, drift: float = 10.0) -> list[float]:
    """Generate synthetic price series with slight upward drift."""
    import random
    random.seed(42)
    closes = [start]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + random.uniform(-0.02, 0.02)) + drift)
    return closes


def make_candles(closes: list[float]) -> list[list]:
    """Wrap closes into Binance klines format."""
    result = []
    for c in closes:
        high = c * 1.01
        low = c * 0.99
        result.append([0, str(c), str(high), str(low), str(c), str(c * 1000), 0, 0, 0, 0, 0, 0])
    return result


# ---- Indicator unit tests ----

def test_sma_correct():
    closes = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _sma(closes, 3) == pytest.approx(4.0)  # (3+4+5)/3


def test_ema_length_preserved():
    closes = make_closes(50)
    ema = _ema(closes, 12)
    assert len(ema) == 50


def test_rsi_range():
    closes = make_closes(100)
    rsi = _rsi(closes, period=14)
    assert 0 <= rsi <= 100


def test_rsi_overbought_on_rising():
    """Consistently rising prices → RSI near 100."""
    closes = [float(i) for i in range(1, 101)]
    rsi = _rsi(closes, period=14)
    assert rsi > 80


def test_rsi_oversold_on_falling():
    """Consistently falling prices → RSI near 0."""
    closes = [float(100 - i) for i in range(100)]
    rsi = _rsi(closes, period=14)
    assert rsi < 20


def test_macd_returns_cross_status():
    closes = make_closes(200)
    macd_line, signal_line, cross = _macd(closes)
    assert isinstance(macd_line, float)
    assert isinstance(signal_line, float)
    assert cross in ("bullish_cross", "bearish_cross", "none")


def test_support_resistance_correct():
    highs = [100.0, 105.0, 110.0, 95.0, 108.0]
    lows = [90.0, 85.0, 92.0, 88.0, 91.0]
    support, resistance = _support_resistance(highs, lows, window=5)
    assert support == 85.0
    assert resistance == 110.0


# ---- get_ta_summary integration tests ----

async def test_get_ta_summary_returns_all_keys():
    closes = make_closes(200)
    mock_resp = MagicMock()
    mock_resp.json.return_value = make_candles(closes)
    mock_resp.raise_for_status = MagicMock()

    with patch("src.content.technical_analysis.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await get_ta_summary("BTC", "1D")

    expected_keys = {
        "symbol", "timeframe", "price", "change_pct", "trend", "signal",
        "rsi", "rsi_zone", "macd", "macd_signal", "macd_cross",
        "ma20", "ma50", "ma200", "price_vs_ma200", "support", "resistance",
    }
    assert expected_keys == set(result.keys())


async def test_get_ta_summary_valid_ranges():
    closes = make_closes(200)
    mock_resp = MagicMock()
    mock_resp.json.return_value = make_candles(closes)
    mock_resp.raise_for_status = MagicMock()

    with patch("src.content.technical_analysis.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await get_ta_summary("ETH", "4H")

    assert 0 <= result["rsi"] <= 100
    assert result["trend"] in ("bullish", "bearish", "neutral")
    assert result["signal"] in ("buy", "sell", "neutral")
    assert result["rsi_zone"] in ("oversold", "neutral", "overbought")
    assert result["macd_cross"] in ("bullish_cross", "bearish_cross", "none")
    assert result["price_vs_ma200"] in ("above", "below")
    assert result["support"] <= result["price"]
    assert result["resistance"] >= result["support"]


async def test_get_ta_summary_raises_on_too_few_candles():
    mock_resp = MagicMock()
    mock_resp.json.return_value = make_candles(make_closes(10))  # Only 10 candles
    mock_resp.raise_for_status = MagicMock()

    with patch("src.content.technical_analysis.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(TAError):
            await get_ta_summary("BTC", "1D")
