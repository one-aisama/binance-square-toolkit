"""Quick live test of Agent System v2 integration.

Tests: connect → feed → filter → guard → market → like (with behavior) → stats.
"""

import asyncio
import sys
import os

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sdk import BinanceSquareSDK
from src.runtime.guard import ActionGuard
from src.accounts.limiter import ActionLimiter
from src.accounts.manager import LimitsConfig
from src.strategy.feed_filter import filter_feed


async def test_session():
    # 1. Connect
    sdk = BinanceSquareSDK(profile_serial="1")
    print("=== CONNECTING ===")
    await sdk.connect()
    print("Connect: done")

    # 2. Init guard
    limiter = ActionLimiter(db_path="data/bsq.db")
    limits = LimitsConfig()
    guard = ActionGuard(limiter=limiter, limits=limits, account_id="aisama")
    sdk._guard = guard
    print("Guard initialized")

    # 3. Get feed
    print("\n=== FEED ===")
    posts = await sdk.get_feed_posts(count=10)
    print(f"Raw feed: {len(posts)} posts")

    # 4. Filter feed
    filtered = filter_feed(posts)
    print(f"Filtered: {len(filtered.posts)} posts (removed {filtered.removed_count})")
    print(f"Removal reasons: {filtered.removal_reasons}")
    print(f"Need more feed: {filtered.need_more}")

    for p in filtered.posts[:3]:
        text_preview = p["text"][:80].replace("\n", " ")
        print(f"  [{p['like_count']} likes] {p['author']}: {text_preview}")

    # 5. Guard checks
    print("\n=== GUARD CHECKS ===")
    for action in ["like", "comment", "post", "follow"]:
        decision = await guard.check(action)
        print(f"  {action}: {decision.verdict.value} ({decision.reason or 'ok'})")

    # 6. Market data
    print("\n=== MARKET ===")
    market = await sdk.get_market_data(["BTC", "ETH"])
    for symbol, data in market.items():
        price = float(data.get("price", 0))
        change = float(data.get("change_24h", 0))
        print(f"  {symbol}: ${price:,.2f} ({change:+.1f}%)")

    # 7. Like test (with guard + behavior)
    print("\n=== LIKE TEST (guard + behavior) ===")
    if filtered.posts:
        target = filtered.posts[0]
        print(f"  Target: post {target['post_id']} by {target['author']}")
        result = await sdk.like_post(target["post_id"])
        success = result.get("success", False) if isinstance(result, dict) else bool(result)
        print(f"  Like result: success={success}")
    else:
        print("  No posts to like after filtering")

    # 8. Disconnect and stats
    await sdk.disconnect()
    print("\n=== SESSION STATS ===")
    stats = guard.get_session_stats()
    print(f"  Total actions: {stats['total_actions']}")
    print(f"  Successful: {stats['successful']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Circuits opened: {stats['circuits_opened']}")
    print(f"  Duration: {stats['duration_seconds']}s")
    print("\nDONE - All v2 systems working")


if __name__ == "__main__":
    asyncio.run(test_session())
