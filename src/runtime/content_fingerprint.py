from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Iterable

MACRO_KEYWORDS = {
    "etf",
    "fed",
    "flows",
    "liquidity",
    "macro",
    "positioning",
    "powell",
    "risk",
    "structure",
    "tape",
}
ROTATION_KEYWORDS = {
    "alt",
    "altcoin",
    "bid",
    "cleaner",
    "leader",
    "listing",
    "relative strength",
    "rotation",
    "sector",
}
TA_KEYWORDS = {
    "1d",
    "4h",
    "breakout",
    "chart",
    "levels",
    "ma20",
    "ma50",
    "macd",
    "resistance",
    "rsi",
    "support",
}
PSYCHOLOGY_KEYWORDS = {
    "certainty",
    "chase",
    "crowd",
    "conviction",
    "emotion",
    "ego",
    "narrative",
    "people",
    "panic",
}
SECURITY_KEYWORDS = {
    "approve",
    "attack",
    "compromised",
    "custody",
    "drain",
    "drainer",
    "exploit",
    "hack",
    "malware",
    "migrate",
    "move it",
    "permissions",
    "phishing",
    "private key",
    "quantum",
    "revoke",
    "risk loss",
    "seed phrase",
    "security",
    "wallet",
}
EDUCATION_KEYWORDS = {
    "advice",
    "beginner",
    "discipline",
    "habit",
    "identity",
    "lesson",
    "mistake",
    "newcomer",
    "principle",
    "process",
    "rule",
}
COMMON_COIN_TICKERS = {
    "AAVE",
    "ADA",
    "ARB",
    "ATOM",
    "AVAX",
    "BCH",
    "BNB",
    "BONK",
    "BTC",
    "DOGE",
    "DOT",
    "ENA",
    "ETH",
    "FET",
    "FIL",
    "FTM",
    "HBAR",
    "HYPE",
    "ICP",
    "INJ",
    "JUP",
    "LINK",
    "LTC",
    "NEAR",
    "NOT",
    "OM",
    "ONDO",
    "OP",
    "PEPE",
    "PYTH",
    "SEI",
    "SHIB",
    "SOL",
    "SUI",
    "TAO",
    "TIA",
    "TON",
    "TRX",
    "UNI",
    "WIF",
    "XLM",
    "XRP",
}
MARKET_NATIVE_KEYWORDS = MACRO_KEYWORDS | ROTATION_KEYWORDS | TA_KEYWORDS | {
    "bounce",
    "breakdown",
    "breakout",
    "follow through",
    "leader",
    "reclaim",
    "retest",
    "squeeze",
    "trend",
}


def extract_primary_coin(
    text: str,
    *,
    coin: str | None = None,
    chart_symbol: str | None = None,
) -> str | None:
    match = re.search(r"\$([A-Z]{2,10})", text or "", re.IGNORECASE)
    if match:
        return match.group(1).upper()
    if coin:
        return str(coin).upper()
    if chart_symbol:
        return str(chart_symbol).split("_", 1)[0].upper()
    return None


def infer_angle(text: str) -> str:
    lowered = str(text or "").lower()
    if any(keyword in lowered for keyword in TA_KEYWORDS):
        return "ta"
    if any(keyword in lowered for keyword in ROTATION_KEYWORDS):
        return "rotation"
    if any(keyword in lowered for keyword in MACRO_KEYWORDS):
        return "macro"
    if any(keyword in lowered for keyword in PSYCHOLOGY_KEYWORDS):
        return "psychology"
    return "general"


def infer_comment_domain(text: str) -> str:
    lowered = str(text or "").lower()
    if any(keyword in lowered for keyword in SECURITY_KEYWORDS):
        return "security"
    if any(keyword in lowered for keyword in TA_KEYWORDS):
        return "ta"
    if any(keyword in lowered for keyword in ROTATION_KEYWORDS):
        return "rotation"
    if any(keyword in lowered for keyword in MACRO_KEYWORDS):
        return "macro"
    if any(keyword in lowered for keyword in PSYCHOLOGY_KEYWORDS):
        return "psychology"
    if any(keyword in lowered for keyword in EDUCATION_KEYWORDS):
        return "education"
    return "general"


def is_market_discussion(text: str) -> bool:
    lowered = str(text or "").lower()
    if extract_primary_coin(text):
        return True
    return any(keyword in lowered for keyword in MARKET_NATIVE_KEYWORDS)


def normalize_text(text: str) -> str:
    collapsed = re.sub(r"[\$#]\w+", "", str(text or "").lower())
    return re.sub(r"\s+", " ", collapsed).strip()


def add_cashtags(text: str, *, known_symbols: Iterable[str] | None = None) -> str:
    """Prefix standalone coin tickers with `$` while leaving other acronyms untouched."""
    raw = str(text or "")
    if not raw:
        return raw

    eligible = {str(symbol).upper() for symbol in (known_symbols or []) if str(symbol).strip()}
    eligible.update(COMMON_COIN_TICKERS)
    if not eligible:
        return raw

    def normalize_existing(match: re.Match[str]) -> str:
        token = match.group(1).upper()
        if token not in eligible:
            return match.group(0)
        return f"${token}"

    raw = re.sub(r"\$([A-Za-z]{2,10})\b", normalize_existing, raw)

    def repl(match: re.Match[str]) -> str:
        token = match.group(1).upper()
        if token not in eligible:
            return match.group(1)
        return f"${token}"

    return re.sub(r"(?<![$#])\b([A-Z]{2,10})\b", repl, raw)


def opening_signature(text: str) -> str:
    paragraph = str(text or "").split("\n\n", 1)[0]
    cleaned = re.sub(r"[\$#]\w+", "", paragraph.lower())
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    tokens = [token for token in cleaned.split() if token]
    return " ".join(tokens[:10])


def format_signature(text: str) -> str:
    stripped = str(text or "").strip()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", stripped) if part.strip()]
    first = paragraphs[0] if paragraphs else ""
    first_words = len(first.split())
    length_bucket = "short" if first_words < 10 else "mid" if first_words < 20 else "long"
    has_cashtag = bool(re.search(r"\$[A-Z]{2,10}", stripped))
    return f"p{len(paragraphs)}:{length_bucket}:q{int('?' in stripped)}:c{int(has_cashtag)}"


def similarity_ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def visual_type_from_action(action: Any) -> str:
    visual_kind = str(getattr(action, "visual_kind", "") or "").lower()
    if visual_kind:
        return visual_kind
    if getattr(action, "chart_image", False):
        return "chart_image"
    if getattr(action, "image_path", None):
        return "image"
    if getattr(action, "coin", None):
        return "chart_card"
    return "text"
