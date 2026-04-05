from src.runtime.content_fingerprint import add_cashtags


def test_add_cashtags_prefixes_known_coin_lists():
    text = "Price predictions 4/1: BTC, ETH, BNB, XRP, SOL, DOGE, HYPE, ADA, BCH, LINK"

    assert add_cashtags(text) == (
        "Price predictions 4/1: $BTC, $ETH, $BNB, $XRP, $SOL, $DOGE, $HYPE, $ADA, $BCH, $LINK"
    )


def test_add_cashtags_leaves_non_coin_acronyms_untouched():
    text = "ETF flows stay weak while BTC tries to hold the level"

    assert add_cashtags(text) == "ETF flows stay weak while $BTC tries to hold the level"


def test_add_cashtags_normalizes_existing_lowercase_cashtags():
    text = "$shib stays noisy while link keeps acting cleaner"

    assert add_cashtags(text, known_symbols=["SHIB", "LINK"]) == "$SHIB stays noisy while link keeps acting cleaner"
