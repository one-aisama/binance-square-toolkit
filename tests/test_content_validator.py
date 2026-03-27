"""Tests for content validator (banned phrases, structure, duplicates)."""

import pytest

from src.content.validator import (
    ValidationResult,
    validate_post,
    validate_comment,
    validate_article,
    validate_quote,
    _check_banned_phrases,
    _check_duplicates,
    _normalize_for_comparison,
    DUPLICATE_THRESHOLD,
)


# ---- ValidationResult ----


class TestValidationResult:
    def test_bool_true_when_valid(self):
        r = ValidationResult(valid=True)
        assert bool(r) is True

    def test_bool_false_when_invalid(self):
        r = ValidationResult(valid=False, errors=["something wrong"])
        assert bool(r) is False

    def test_defaults_empty_lists(self):
        r = ValidationResult(valid=True)
        assert r.errors == []
        assert r.warnings == []


# ---- Banned Phrases ----


class TestBannedPhrases:
    def test_finds_banned_phrase(self):
        found = _check_banned_phrases("Let's dive into the market today!")
        assert "let's dive into" in found

    def test_case_insensitive(self):
        found = _check_banned_phrases("This is a GAME-CHANGER for crypto!")
        assert "game-changer" in found

    def test_clean_text_passes(self):
        found = _check_banned_phrases(
            "$BTC reclaimed 70k. volume looking strong on the daily chart"
        )
        assert found == []

    def test_multiple_banned_phrases(self):
        found = _check_banned_phrases(
            "Let's dive into this unprecedented paradigm shift in crypto"
        )
        assert len(found) >= 3

    def test_partial_match_works(self):
        """Banned phrases are substring matches, not exact word matches."""
        found = _check_banned_phrases("oh man this is truly unprecedented and wild")
        assert "unprecedented" in found


# ---- Duplicate Detection ----


class TestDuplicateDetection:
    def test_identical_text_detected(self):
        text = "$BTC looking strong on the daily. RSI above 60, MACD crossing up."
        ratio = _check_duplicates(text, [text])
        assert ratio is not None
        assert ratio >= DUPLICATE_THRESHOLD

    def test_different_text_passes(self):
        text = "$BTC looking strong on the daily"
        recent = ["$ETH gas fees are dropping, L2s eating Ethereum's lunch"]
        ratio = _check_duplicates(text, recent)
        assert ratio is None

    def test_similar_text_different_ticker_detected(self):
        """Same structure with different $CASHTAG should still be caught."""
        text = "$BTC is pumping hard today, volume up 30% and RSI is overbought at 75"
        recent = [
            "$ETH is pumping hard today, volume up 30% and RSI is overbought at 75"
        ]
        ratio = _check_duplicates(text, recent)
        assert ratio is not None

    def test_normalize_strips_cashtags(self):
        result = _normalize_for_comparison("$BTC and $ETH are pumping #crypto")
        assert "$" not in result
        assert "#" not in result

    def test_empty_recent_posts(self):
        ratio = _check_duplicates("some text", [])
        assert ratio is None


# ---- validate_post ----


class TestValidatePost:
    def test_valid_post_passes(self):
        text = (
            "$BTC just reclaimed 70k and volume is picking up on the 4h chart. "
            "RSI at 62, not overbought yet.\n\n"
            "watching 72k resistance next. if it breaks with volume, "
            "we could see a push to ATH territory. #Bitcoin #crypto"
        )
        result = validate_post(text)
        assert result.valid is True
        assert result.errors == []

    def test_too_short_fails(self):
        result = validate_post("$BTC is up")
        assert result.valid is False
        assert any("too short" in e for e in result.errors)

    def test_single_paragraph_fails(self):
        text = (
            "$BTC just broke 70k and volume is insane right now. "
            "RSI overbought but momentum is strong. watching for continuation."
        )
        result = validate_post(text)
        assert result.valid is False
        assert any("2 paragraphs" in e for e in result.errors)

    def test_banned_phrase_fails(self):
        text = (
            "Let's dive into the $BTC chart today and see whats happening.\n\n"
            "Support at 68k, resistance at 72k. Classic range bound action."
        )
        result = validate_post(text)
        assert result.valid is False
        assert any("Banned phrases" in e for e in result.errors)

    def test_no_cashtag_warns(self):
        text = (
            "market looking choppy today. no clear direction on the daily chart.\n\n"
            "probably best to sit on hands and wait for a clean setup. "
            "patience pays more than FOMO."
        )
        result = validate_post(text)
        assert result.valid is True
        assert any("CASHTAG" in w for w in result.warnings)

    def test_duplicate_fails(self):
        text = (
            "$BTC just broke 70k and the daily looks incredible. "
            "momentum is real.\n\n"
            "watching for a retest of 68k as support. if it holds, 75k next."
        )
        recent = [text]
        result = validate_post(text, recent_posts=recent)
        assert result.valid is False
        assert any("similar" in e.lower() for e in result.errors)

    def test_no_recent_posts_skips_duplicate_check(self):
        text = (
            "$BTC at 70k. chart structure looks clean.\n\n"
            "MAs all aligned bullish. this is the setup traders wait for."
        )
        result = validate_post(text, recent_posts=None)
        assert result.valid is True


# ---- validate_comment ----


class TestValidateComment:
    def test_valid_comment_passes(self):
        result = validate_comment(
            "the part about eth gas fees is spot on but L2 adoption "
            "is fixing that faster than people think"
        )
        assert result.valid is True

    def test_too_short_fails(self):
        result = validate_comment("ok")
        assert result.valid is False

    def test_generic_great_post_fails(self):
        result = validate_comment("Great post!")
        assert result.valid is False
        assert any("Generic" in e for e in result.errors)

    def test_generic_thanks_sharing_fails(self):
        result = validate_comment("Thanks for sharing!")
        assert result.valid is False

    def test_generic_nice_analysis_fails(self):
        result = validate_comment("Nice analysis, keep it up!")
        assert result.valid is False

    def test_generic_very_informative_fails(self):
        result = validate_comment("Very informative!")
        assert result.valid is False

    def test_banned_phrase_in_comment_fails(self):
        result = validate_comment(
            "This is truly a game-changer for DeFi protocols"
        )
        assert result.valid is False

    def test_substantive_agreement_passes(self):
        result = validate_comment(
            "yeah SOL fees are crazy low but the network went down "
            "twice this month so theres that"
        )
        assert result.valid is True


# ---- validate_article ----


class TestValidateArticle:
    def test_valid_article_passes(self):
        title = "$BTC Weekly Analysis: Testing Key Resistance"
        body = (
            "$BTC has been consolidating in a tight range between 68k and 72k "
            "for the past week. Volume is declining which usually precedes a "
            "big move.\n\n"
            "On the daily chart, RSI is neutral at 52 and MACD is flat. "
            "No clear signal yet. The 200-day MA at 65k provides strong "
            "support below.\n\n"
            "Key levels to watch: 72k resistance (tested 3 times), 68k support, "
            "and the 200-day MA at 65k as the last line of defense. A break "
            "above 72k with volume would be very bullish. A break below 68k "
            "opens the door to 65k."
        )
        result = validate_article(title, body)
        assert result.valid is True

    def test_short_title_fails(self):
        result = validate_article("BTC", "x" * 400)
        assert result.valid is False
        assert any("Title too short" in e for e in result.errors)

    def test_short_body_fails(self):
        result = validate_article(
            "A Good Title For Article", "Short body here."
        )
        assert result.valid is False
        assert any("body too short" in e for e in result.errors)

    def test_banned_phrase_in_title_fails(self):
        result = validate_article(
            "A Comprehensive Guide to $BTC Trading",
            "x" * 400,
        )
        assert result.valid is False
        assert any("title" in e.lower() for e in result.errors)

    def test_banned_phrase_in_body_fails(self):
        title = "Weekly Market Wrap"
        body = (
            "This week was interesting for crypto markets.\n\n"
            "Let's dive into the details of what happened with $BTC and $ETH."
            "\n\n" + "More analysis here. " * 30
        )
        result = validate_article(title, body)
        assert result.valid is False
        assert any("body" in e.lower() for e in result.errors)


# ---- validate_quote ----


class TestValidateQuote:
    def test_valid_quote_passes(self):
        text = (
            "interesting take but the data tells a different story. "
            "$BTC on-chain metrics show accumulation, not distribution.\n\n"
            "whales have been buying the dip consistently. "
            "the 30-day SOPR is below 1 which historically means "
            "we're near a local bottom."
        )
        result = validate_quote(text)
        assert result.valid is True

    def test_too_short_fails(self):
        result = validate_quote("I agree with this")
        assert result.valid is False

    def test_single_paragraph_fails(self):
        text = (
            "interesting take but I think the market is actually heading "
            "lower based on the weekly RSI divergence and declining volume."
        )
        result = validate_quote(text)
        assert result.valid is False
        assert any("2 paragraphs" in e for e in result.errors)

    def test_banned_phrase_fails(self):
        text = (
            "This is truly unprecedented in the history of crypto.\n\n"
            "We've never seen anything like this before and it changes "
            "everything."
        )
        result = validate_quote(text)
        assert result.valid is False
