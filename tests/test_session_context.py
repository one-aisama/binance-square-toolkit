from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.runtime.session_context import SessionContextBuilder
from tests.helpers import make_agent


def test_example_altcoin_feed_prioritization_prefers_altcoin_threads():
    builder = SessionContextBuilder("agents/example_altcoin")
    prepared = builder._prepare_posts(
        [
            {
                "post_id": "macro-1",
                "author": "macrocat",
                "text": "$BTC bounce is all ETF flows and Powell timing right now so the market keeps overreacting",
                "like_count": 240,
            },
            {
                "post_id": "alt-1",
                "author": "altqueen",
                "text": "$SOL still has the cleanest relative strength in this rotation and Binance alts finally have real bids",
                "like_count": 120,
            },
        ],
        "recommended",
    )
    agent = make_agent(
        "example_altcoin",
        market_symbols=["SOL", "LINK", "AVAX"],
        primary_feed_tab="recommended",
    )

    prioritized = builder._prioritize_posts(prepared, agent)

    assert prioritized[0].post_id == "alt-1"
    assert "preferred_alt:SOL" in prioritized[0].selection_reason


def test_example_macro_feed_prioritization_prefers_btc_macro_threads():
    builder = SessionContextBuilder("agents/example_macro")
    prepared = builder._prepare_posts(
        [
            {
                "post_id": "alt-1",
                "author": "altqueen",
                "text": "$ARB rotation is back because listings and sector momentum are waking up again",
                "like_count": 180,
            },
            {
                "post_id": "macro-1",
                "author": "macrocat",
                "text": "$BTC still looks fragile because ETF flows and liquidity conditions have not improved enough",
                "like_count": 150,
            },
        ],
        "recommended",
    )
    agent = make_agent(
        "example_macro",
        market_symbols=["BTC", "ETH", "SOL"],
        primary_feed_tab="recommended",
    )

    prioritized = builder._prioritize_posts(prepared, agent)

    assert prioritized[0].post_id == "macro-1"
    assert any(kw in prioritized[0].selection_reason for kw in ("btc", "macro", "etf"))



## test_build_can_skip_feed_and_replies removed — tested nonexistent API params (include_replies/include_feed)
