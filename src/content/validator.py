"""Content validator — checks text before publishing.

Validates posts, comments, and articles against content rules:
- Banned phrases (AI cliches, marketing fluff)
- Minimum structure (paragraphs, length)
- $CASHTAG presence for coin-related posts
- Duplicate detection against recent posts

Used by SDK before create_post() and create_article().
"""

import logging
import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import yaml

logger = logging.getLogger("bsq.validator")


def _load_banned_phrases() -> list[str]:
    """Load banned phrases from config/content_rules.yaml (Single Source of Truth)."""
    config_path = Path(__file__).parent.parent.parent / "config" / "content_rules.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        return rules.get("style", {}).get("banned_phrases", [])
    except Exception as e:
        logger.error(f"_load_banned_phrases: failed to load {config_path}: {e}")
        # Fallback — never silently skip validation
        return [
            "let's dive into", "unlock your potential", "game-changer",
            "unprecedented", "paradigm shift", "comprehensive guide",
            "stay tuned", "don't miss out",
        ]


# Loaded once at import time from YAML
BANNED_PHRASES: list[str] = _load_banned_phrases()

# Pre-compiled patterns for performance
_BANNED_PATTERNS: list[re.Pattern] = [
    re.compile(re.escape(phrase), re.IGNORECASE) for phrase in BANNED_PHRASES
]

# Generic comment patterns that add no value
BAD_COMMENT_PATTERNS = [
    re.compile(r"^great\s+post[.!]*$", re.IGNORECASE),
    re.compile(r"^thanks\s+for\s+sharing[.!]*$", re.IGNORECASE),
    re.compile(r"^very\s+informative[.!]*$", re.IGNORECASE),
    re.compile(r"^nice\s+analysis[,.]?\s*(keep\s+it\s+up)?[.!]*$", re.IGNORECASE),
    re.compile(r"^i\s+agree\s+with\s+everything\s+you\s+said[.!]*$", re.IGNORECASE),
]

# Similarity threshold for duplicate detection (0.0 - 1.0)
DUPLICATE_THRESHOLD = 0.65
RECENT_TOPIC_WINDOW = 3
TA_KEYWORDS = {"rsi", "macd", "support", "resistance", "ma20", "ma50", "ma200", "daily chart", "4h", "1d", "chart", "levels"}
NEWS_KEYWORDS = {"roadmap", "news", "headline", "law", "regulation", "announced", "builders", "project", "act", "report", "fragmentation"}
META_KEYWORDS = {"people", "market", "process", "attention", "feed", "traders", "everyone", "conviction"}


@dataclass
class ValidationResult:
    """Result of content validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


def validate_post(text: str, recent_posts: list[str] | None = None) -> ValidationResult:
    """Validate a post before publishing.

    Checks:
    - No banned phrases
    - Minimum 2 paragraphs
    - Minimum 80 characters
    - Not a duplicate of recent posts

    Args:
        text: Post text to validate
        recent_posts: Optional list of recent post texts for duplicate check

    Returns:
        ValidationResult with valid flag, errors, and warnings
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Banned phrases
    found = _check_banned_phrases(text)
    if found:
        errors.append(f"Banned phrases found: {', '.join(found)}")

    # Minimum length
    if len(text.strip()) < 80:
        errors.append(f"Post too short ({len(text.strip())} chars, minimum 80)")

    # Minimum 2 paragraphs (split by double newline or single newline with blank line)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n{2,}", text) if p.strip()]
    if len(paragraphs) < 2:
        errors.append(f"Post needs at least 2 paragraphs (found {len(paragraphs)})")

    # $CASHTAG check — warn if no cashtags found (not an error, some posts are general)
    if not re.search(r"\$[A-Z]{2,10}", text):
        warnings.append("No $CASHTAG found — post won't appear in coin-specific feeds")

    # Duplicate and sequencing checks
    if recent_posts:
        dup = _check_duplicates(text, recent_posts)
        if dup:
            errors.append(f"Too similar to a recent post (similarity: {dup:.0%})")

        topic_repeat = _check_topic_repeat(text, recent_posts)
        if topic_repeat:
            errors.append(topic_repeat)

    valid = len(errors) == 0
    if not valid:
        logger.warning(f"validate_post: {len(errors)} errors — {errors}")
    return ValidationResult(valid=valid, errors=errors, warnings=warnings)


def validate_comment(text: str) -> ValidationResult:
    """Validate a comment before posting.

    Checks:
    - No banned phrases
    - Not a generic empty comment ("Great post!", "Thanks for sharing!")
    - Reasonable length (5-500 chars)

    Args:
        text: Comment text to validate

    Returns:
        ValidationResult
    """
    errors: list[str] = []
    warnings: list[str] = []

    stripped = text.strip()

    # Length
    if len(stripped) < 5:
        errors.append(f"Comment too short ({len(stripped)} chars)")
    elif len(stripped) > 500:
        warnings.append(f"Comment very long ({len(stripped)} chars) — keep it conversational")

    # Banned phrases
    found = _check_banned_phrases(text)
    if found:
        errors.append(f"Banned phrases found: {', '.join(found)}")

    # Generic comment check
    for pattern in BAD_COMMENT_PATTERNS:
        if pattern.match(stripped):
            errors.append(f"Generic comment detected — add substance")
            break

    valid = len(errors) == 0
    return ValidationResult(valid=valid, errors=errors, warnings=warnings)


def validate_article(title: str, body: str) -> ValidationResult:
    """Validate an article before publishing.

    Checks:
    - Title: 10-200 chars, no banned phrases
    - Body: minimum 300 chars, no banned phrases
    - Body has structure (multiple paragraphs)

    Args:
        title: Article title
        body: Article body text

    Returns:
        ValidationResult
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Title checks
    title_stripped = title.strip()
    if len(title_stripped) < 10:
        errors.append(f"Title too short ({len(title_stripped)} chars, minimum 10)")
    if len(title_stripped) > 200:
        errors.append(f"Title too long ({len(title_stripped)} chars, maximum 200)")

    found_title = _check_banned_phrases(title)
    if found_title:
        errors.append(f"Banned phrases in title: {', '.join(found_title)}")

    # Body checks
    body_stripped = body.strip()
    if len(body_stripped) < 300:
        errors.append(f"Article body too short ({len(body_stripped)} chars, minimum 300)")

    found_body = _check_banned_phrases(body)
    if found_body:
        errors.append(f"Banned phrases in body: {', '.join(found_body)}")

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n{2,}", body) if p.strip()]
    if len(paragraphs) < 3:
        warnings.append(f"Article has only {len(paragraphs)} paragraphs — consider adding more structure")

    if not re.search(r"\$[A-Z]{2,10}", body):
        warnings.append("No $CASHTAG in article body")

    valid = len(errors) == 0
    if not valid:
        logger.warning(f"validate_article: {len(errors)} errors — {errors}")
    return ValidationResult(valid=valid, errors=errors, warnings=warnings)


def validate_quote(comment: str) -> ValidationResult:
    """Validate a quote repost comment.

    Checks:
    - Minimum 2 paragraphs (like a post)
    - No banned phrases
    - Minimum 80 chars

    Args:
        comment: Quote comment text

    Returns:
        ValidationResult
    """
    errors: list[str] = []
    warnings: list[str] = []

    stripped = comment.strip()

    if len(stripped) < 80:
        errors.append(f"Quote comment too short ({len(stripped)} chars, minimum 80)")

    found = _check_banned_phrases(comment)
    if found:
        errors.append(f"Banned phrases found: {', '.join(found)}")

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n{2,}", comment) if p.strip()]
    if len(paragraphs) < 2:
        errors.append(f"Quote needs at least 2 paragraphs (found {len(paragraphs)})")

    valid = len(errors) == 0
    return ValidationResult(valid=valid, errors=errors, warnings=warnings)


# ---- Internal helpers ----


def _check_banned_phrases(text: str) -> list[str]:
    """Return list of banned phrases found in text."""
    found = []
    for pattern, phrase in zip(_BANNED_PATTERNS, BANNED_PHRASES):
        if pattern.search(text):
            found.append(phrase)
    return found


def _check_duplicates(text: str, recent_posts: list[str]) -> float | None:
    """Check if text is too similar to any recent post.

    Returns similarity ratio if above threshold, None otherwise.
    """
    # Normalize for comparison
    normalized = _normalize_for_comparison(text)

    for post in recent_posts:
        post_normalized = _normalize_for_comparison(post)
        ratio = SequenceMatcher(None, normalized, post_normalized).ratio()
        if ratio >= DUPLICATE_THRESHOLD:
            return ratio

    return None


def _check_topic_repeat(text: str, recent_posts: list[str]) -> str | None:
    """Block consecutive posts with the same dominant coin and angle."""
    current_signature = _build_topic_signature(text)
    if current_signature is None:
        return None

    for post in recent_posts[:RECENT_TOPIC_WINDOW]:
        recent_signature = _build_topic_signature(post)
        if recent_signature != current_signature:
            break

        coin, angle = current_signature
        return f"Latest profile post already uses the same topic pattern ({coin}, {angle})"

    return None


def _build_topic_signature(text: str) -> tuple[str, str] | None:
    """Infer a coarse topic fingerprint from coin + post angle."""
    primary_coin = _extract_primary_coin(text)
    angle = _infer_post_angle(text)
    if primary_coin and angle != "general":
        return primary_coin, angle
    return None


def _extract_primary_coin(text: str) -> str | None:
    match = re.search(r"\$([A-Z]{2,10})", text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).upper()


def _infer_post_angle(text: str) -> str:
    lowered = text.lower()
    if any(keyword in lowered for keyword in TA_KEYWORDS):
        return "ta"
    if any(keyword in lowered for keyword in NEWS_KEYWORDS):
        return "news"
    if any(keyword in lowered for keyword in META_KEYWORDS):
        return "meta"
    return "general"


def _normalize_for_comparison(text: str) -> str:
    """Normalize text for duplicate comparison.

    Strips cashtags, hashtags, whitespace, and lowercases.
    This way posts about the same topic with different tickers
    are still detected as duplicates.
    """
    text = text.lower()
    text = re.sub(r"[\$#]\w+", "", text)  # Remove $CASHTAGS and #hashtags
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---- Price verification ----

# Pattern: $65,500 or $65500 or $2,023.39 or $0.0028
_PRICE_PATTERN = re.compile(r"\$([0-9][0-9,]*\.?\d*)")


def verify_prices(text: str, market_data: dict[str, dict]) -> list[str]:
    """Check that dollar prices in text are close to actual market data.

    Finds all $X,XXX patterns in text, tries to match them to known coin prices,
    and flags any that are >10% off.

    Args:
        text: Post/comment text
        market_data: {symbol: {price: float, ...}} from get_market_data()

    Returns:
        List of warning strings. Empty = all prices ok.
    """
    warnings = []
    matches = _PRICE_PATTERN.findall(text)
    if not matches or not market_data:
        return warnings

    # Build price lookup: {price_float: symbol}
    known_prices = {}
    for symbol, data in market_data.items():
        if isinstance(data, dict) and "price" in data:
            known_prices[symbol] = float(data["price"])

    for raw_match in matches:
        try:
            mentioned_price = float(raw_match.replace(",", ""))
        except ValueError:
            continue

        # Try to match this price to a known coin
        for symbol, actual_price in known_prices.items():
            if actual_price == 0:
                continue
            # Check if mentioned price is in the same order of magnitude
            ratio = mentioned_price / actual_price
            if 0.1 < ratio < 10:  # same ballpark
                deviation = abs(mentioned_price - actual_price) / actual_price
                if deviation > 0.10:  # >10% off
                    warnings.append(
                        f"Price ${raw_match} may be stale for {symbol} "
                        f"(actual: ${actual_price:,.2f}, deviation: {deviation:.0%})"
                    )
    return warnings

