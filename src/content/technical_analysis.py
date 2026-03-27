"""Technical analysis for crypto assets using Binance klines data.

Fetches OHLCV candles from Binance public API and computes indicators:
RSI, MACD, Moving Averages, support/resistance levels.

No API key required. No external TA libraries — pure Python math.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger("bsq.content")

KLINES_URL = "https://api.binance.com/api/v3/klines"

TIMEFRAME_MAP = {
    "1H": "1h",
    "4H": "4h",
    "1D": "1d",
    "1W": "1w",
}


async def get_ta_summary(symbol: str = "BTC", timeframe: str = "1D") -> dict[str, Any]:
    """Compute technical analysis summary for a trading pair.

    Fetches 200 candles from Binance and computes key indicators.
    Agent uses this as a basis for forming its own market view.

    Args:
        symbol: Coin symbol, e.g. "BTC", "ETH", "SOL"
        timeframe: "1H", "4H", "1D" (default), "1W"

    Returns:
        {
            symbol, timeframe,
            price: float,               # Current close price
            change_pct: float,          # % change over last candle
            trend: str,                 # "bullish" | "bearish" | "neutral"
            signal: str,                # "buy" | "sell" | "neutral"
            rsi: float,                 # 0-100
            rsi_zone: str,              # "oversold" | "neutral" | "overbought"
            macd: float,                # MACD line value
            macd_signal: float,         # Signal line value
            macd_cross: str,            # "bullish_cross" | "bearish_cross" | "none"
            ma20: float,
            ma50: float,
            ma200: float,
            price_vs_ma200: str,        # "above" | "below"
            support: float,             # Recent support level
            resistance: float,          # Recent resistance level
        }
    """
    tf = TIMEFRAME_MAP.get(timeframe, "1d")
    pair = f"{symbol.upper()}USDT"

    candles = await _fetch_klines(pair, tf, limit=200)
    if len(candles) < 50:
        raise TAError(f"Not enough candles for {pair} ({len(candles)} fetched)")

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    price = closes[-1]
    prev_close = closes[-2]
    change_pct = round((price - prev_close) / prev_close * 100, 2)

    rsi = _rsi(closes, period=14)
    macd_line, signal_line, macd_cross = _macd(closes)
    ma20 = _sma(closes, 20)
    ma50 = _sma(closes, 50)
    ma200 = _sma(closes, 200)
    support, resistance = _support_resistance(highs, lows, window=20)

    rsi_zone = "oversold" if rsi < 35 else "overbought" if rsi > 70 else "neutral"
    price_vs_ma200 = "above" if price > ma200 else "below"

    # Trend: price position relative to MAs
    above_count = sum([price > ma20, price > ma50, price > ma200])
    trend = "bullish" if above_count >= 2 else "bearish" if above_count <= 1 else "neutral"

    # Signal: combines RSI + MACD cross
    signal = "neutral"
    if macd_cross == "bullish_cross" and rsi < 65:
        signal = "buy"
    elif macd_cross == "bearish_cross" and rsi > 40:
        signal = "sell"
    elif rsi < 30:
        signal = "buy"
    elif rsi > 75:
        signal = "sell"

    result = {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "price": price,
        "change_pct": change_pct,
        "trend": trend,
        "signal": signal,
        "rsi": round(rsi, 2),
        "rsi_zone": rsi_zone,
        "macd": round(macd_line, 4),
        "macd_signal": round(signal_line, 4),
        "macd_cross": macd_cross,
        "ma20": round(ma20, 2),
        "ma50": round(ma50, 2),
        "ma200": round(ma200, 2),
        "price_vs_ma200": price_vs_ma200,
        "support": round(support, 2),
        "resistance": round(resistance, 2),
    }
    logger.info(f"TA summary for {pair} {timeframe}: trend={trend}, rsi={result['rsi']}, signal={signal}")
    return result


# ---- Data fetching ----

async def _fetch_klines(pair: str, interval: str, limit: int = 200) -> list[dict[str, float]]:
    """Fetch OHLCV candles from Binance public API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            KLINES_URL,
            params={"symbol": pair, "interval": interval, "limit": limit},
        )
        resp.raise_for_status()
        raw = resp.json()

    return [
        {
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        }
        for c in raw
    ]


# ---- Indicators ----

def _sma(values: list[float], period: int) -> float:
    """Simple Moving Average."""
    return sum(values[-period:]) / period


def _ema(values: list[float], period: int) -> list[float]:
    """Exponential Moving Average — returns full series."""
    k = 2 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def _rsi(closes: list[float], period: int = 14) -> float:
    """Relative Strength Index."""
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(closes: list[float]) -> tuple[float, float, str]:
    """MACD line, signal line, and cross direction.

    Returns:
        (macd_line, signal_line, cross): cross is "bullish_cross" | "bearish_cross" | "none"
    """
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_series = [ema12[i] - ema26[i] for i in range(len(closes))]
    signal_series = _ema(macd_series, 9)

    macd_now = macd_series[-1]
    signal_now = signal_series[-1]
    macd_prev = macd_series[-2]
    signal_prev = signal_series[-2]

    cross = "none"
    if macd_prev < signal_prev and macd_now > signal_now:
        cross = "bullish_cross"
    elif macd_prev > signal_prev and macd_now < signal_now:
        cross = "bearish_cross"

    return macd_now, signal_now, cross


def _support_resistance(
    highs: list[float], lows: list[float], window: int = 20
) -> tuple[float, float]:
    """Recent support and resistance levels from last N candles."""
    recent_highs = highs[-window:]
    recent_lows = lows[-window:]
    return min(recent_lows), max(recent_highs)


class TAError(Exception):
    """Raised when technical analysis cannot be computed."""
    pass
