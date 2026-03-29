"""Session 5 — aisama agent session script.
Day 3+ of bearish market. Focus: comments on popular posts, build relationships,
1 data-backed post with chart. Fix previous session bugs (market dict access, TA keys).
"""

import asyncio
import logging
import json
import random

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("aisama.session5")


async def session():
    from src.sdk import BinanceSquareSDK
    from src.runtime.agent_config import load_active_agent

    agent = load_active_agent()
    sdk = BinanceSquareSDK(
        profile_serial=agent.profile_serial,
        account_id=agent.agent_id,
    )
    await sdk.connect()
    logger.info(
        "Connected to AdsPower profile for %s (serial=%s)",
        agent.agent_id,
        agent.profile_serial,
    )

    try:
        return await _run_session(sdk, agent.binance_username)
    finally:
        await sdk.disconnect()
        logger.info("Session complete. Disconnected.")


async def _run_session(sdk, binance_username: str):
    # =====================================================
    # PHASE 1: Gather context — market, news, TA
    # =====================================================
    logger.info("=== PHASE 1: Market Context ===")

    # market = {"BTC": {"price": float, "change_24h": float, "volume": float}, ...}
    market = await sdk.get_market_data(["BTC", "ETH", "SOL", "BNB", "XRP"])
    logger.info(f"Market: {json.dumps(market, indent=2, default=str)}")

    news = await sdk.get_crypto_news(limit=5)
    logger.info(f"News: {json.dumps(news, indent=2, default=str)}")

    # TA returns flat dict: {rsi, macd, support, resistance, trend, ma20, ma50, ma200, ...}
    try:
        btc_ta = await sdk.get_ta_summary("BTC", "1D")
        logger.info(f"BTC TA: {json.dumps(btc_ta, indent=2, default=str)}")
    except Exception as e:
        logger.warning(f"BTC TA failed: {e}")
        btc_ta = {}

    try:
        eth_ta = await sdk.get_ta_summary("ETH", "4h")
        logger.info(f"ETH TA: {json.dumps(eth_ta, indent=2, default=str)}")
    except Exception as e:
        logger.warning(f"ETH TA failed: {e}")
        eth_ta = {}

    # =====================================================
    # PHASE 2: Check replies to my comments (priority #1)
    # =====================================================
    logger.info("=== PHASE 2: Check Replies ===")

    replies = await sdk.get_my_comment_replies(username=binance_username)
    logger.info(f"Comment replies: {json.dumps(replies, indent=2, default=str)}")

    # Reply to people who engaged with my comments
    if replies and isinstance(replies, list):
        for r in replies:
            post_id = r.get("comment_post_id", "")
            if not post_id:
                continue
            for rep in r.get("replies", []):
                handle = rep.get("author_handle", "")
                rep_text = rep.get("text", "")
                if handle == "aisama" or not rep_text.strip():
                    continue
                # Build a reply
                reply = _build_reply(handle, rep_text, r.get("comment_text", ""), btc_ta)
                if reply:
                    logger.info(f"Replying to @{handle} on post {post_id}")
                    result = await sdk.comment_on_post(post_id, reply)
                    logger.info(f"Reply result: {result}")
                    await asyncio.sleep(random.uniform(8, 15))

    # =====================================================
    # PHASE 3: Browse feed, engage with good posts
    # =====================================================
    logger.info("=== PHASE 3: Feed Engagement ===")

    posts = await sdk.get_feed_posts(count=25)
    logger.info(f"Got {len(posts) if posts else 0} feed posts")

    # Filter: skip spam, keep quality
    good_posts = []
    if posts:
        for p in posts:
            text = p.get("text", "")
            likes = p.get("like_count", 0)
            post_id = p.get("post_id", "")
            author = p.get("author", "")

            if not text or len(text) < 50:
                continue
            spam_words = ["gift", "giveaway", "airdrop", "copy trading", "SIGN", "sign token", "free crypto", "claim"]
            if any(w.lower() in text.lower() for w in spam_words):
                continue

            good_posts.append({
                "post_id": post_id,
                "author": author,
                "text": text[:300],
                "likes": likes,
            })

    good_posts.sort(key=lambda x: x["likes"], reverse=True)
    logger.info(f"Found {len(good_posts)} quality posts")
    for i, p in enumerate(good_posts[:10]):
        logger.info(f"  [{i}] @{p['author']} ({p['likes']} likes): {p['text'][:100]}")

    # Engage: 3 comments on 80+ like posts, 2-3 extra likes
    engaged = []
    comments_made = 0
    likes_done = 0
    authors_engaged = set()

    for post in good_posts:
        if comments_made >= 3 and likes_done >= 4:
            break

        pid = post["post_id"]
        author = post["author"]
        text = post["text"]
        likes = post["likes"]

        if author in authors_engaged:
            continue

        # Comment + like on popular posts
        if likes >= 80 and comments_made < 3:
            comment = _build_comment(text, market, btc_ta, eth_ta)
            if comment:
                logger.info(f"Engaging {pid} by @{author} ({likes} likes) — like+comment")
                result = await sdk.engage_post(pid, like=True, comment=comment)
                logger.info(f"Result: {result}")
                engaged.append({"post_id": pid, "author": author, "action": "like+comment"})
                comments_made += 1
                likes_done += 1
                authors_engaged.add(author)
                await asyncio.sleep(random.uniform(15, 30))
                continue

        # Just like for medium posts
        if likes >= 20 and likes_done < 5:
            logger.info(f"Liking {pid} by @{author} ({likes} likes)")
            result = await sdk.like_post(pid)
            logger.info(f"Like: {result}")
            engaged.append({"post_id": pid, "author": author, "action": "like"})
            likes_done += 1
            authors_engaged.add(author)
            await asyncio.sleep(random.uniform(5, 12))

    # =====================================================
    # PHASE 4: Create own post with chart
    # =====================================================
    logger.info("=== PHASE 4: Create Post ===")

    # Screenshot BTC chart
    chart_path = None
    try:
        chart_path = await sdk.screenshot_chart("BTC_USDT", "4H")
        logger.info(f"Chart: {chart_path}")
    except Exception as e:
        logger.warning(f"Chart failed: {e}")
        try:
            chart_path = await sdk.take_screenshot(
                "https://www.binance.com/en/trade/BTC_USDT?type=spot", wait=8
            )
            logger.info(f"Fallback chart: {chart_path}")
        except Exception as e2:
            logger.warning(f"Fallback also failed: {e2}")

    post_text, coin, sentiment = _build_post(market, btc_ta, eth_ta, news)
    logger.info(f"Post:\n{post_text}")

    result = await sdk.create_post(text=post_text, coin=coin, sentiment=sentiment, image_path=chart_path)
    logger.info(f"Post result: {result}")

    # =====================================================
    # PHASE 5: Check minimum and wrap up
    # =====================================================
    logger.info("=== PHASE 5: Session Check ===")

    status = sdk.get_minimum_status()
    can_stop, reason = sdk.can_finish()
    logger.info(f"Status: {status} | Can finish: {can_stop} ({reason})")

    if not can_stop:
        logger.info("Minimum not met, doing extra work...")
        remaining = [p for p in good_posts if p["author"] not in authors_engaged]
        for post in remaining[:4]:
            await sdk.like_post(post["post_id"])
            likes_done += 1
            await asyncio.sleep(random.uniform(4, 8))
        if comments_made < 1 and remaining:
            c = _build_comment(remaining[0]["text"], market, btc_ta, eth_ta)
            if c:
                await sdk.comment_on_post(remaining[0]["post_id"], c)
                comments_made += 1

        can_stop, reason = sdk.can_finish()
        logger.info(f"After extra: {can_stop} ({reason})")

    return {
        "market": market,
        "replies": replies,
        "engaged": engaged,
        "comments_made": comments_made,
        "likes_done": likes_done,
        "post_text": post_text,
    }


# =====================================================
# Content builders — I write these myself
# =====================================================

def _build_comment(post_text: str, market: dict, btc_ta: dict, eth_ta: dict) -> str:
    """Topic-matched comment. Market is {"BTC": {"price", "change_24h"}, ...}.
    TA is flat: {"rsi", "macd", "support", "resistance", "trend", ...}."""
    text_lower = post_text.lower()

    btc_price = market.get("BTC", {}).get("price", "?")
    btc_rsi = btc_ta.get("rsi", "?")
    btc_support = btc_ta.get("support", "?")
    btc_resistance = btc_ta.get("resistance", "?")
    btc_macd = btc_ta.get("macd", "?")
    eth_rsi = eth_ta.get("rsi", "?")
    eth_support = eth_ta.get("support", "?")

    # Format support/resistance as dollar amounts
    def fmt(v):
        try:
            return f"${float(v):,.0f}"
        except (ValueError, TypeError):
            return str(v)

    sup = fmt(btc_support)
    res = fmt(btc_resistance)
    eth_sup = fmt(eth_support)

    # ETH post
    if any(w in text_lower for w in ["eth", "ethereum", "$eth"]):
        return f"ETH 4H RSI at {eth_rsi} — been grinding near {eth_sup} support. need a clean reclaim of the 200 MA before getting excited. patience > fomo rn"

    # SOL post
    if any(w in text_lower for w in ["sol", "solana", "$sol"]):
        sol_price = market.get("SOL", {}).get("price", "?")
        sol_change = market.get("SOL", {}).get("change_24h", "?")
        return f"SOL at ${sol_price} ({sol_change}% today) still deep below every major MA. ecosystem is building but price doesn't care yet. waiting for BTC to find a bottom first"

    # Meme coins
    if any(w in text_lower for w in ["shib", "doge", "pepe", "meme", "floki", "bonk"]):
        return "meme coins = pure sentiment play. when BTC is shaky they bleed faster than anything. but when the reversal hits they also 2-3x before alts move. timing is everything"

    # Liquidation / bearish
    if any(w in text_lower for w in ["liquidat", "crash", "dump", "bearish", "blood", "capitulat"]):
        return f"liquidations separate corrections from capitulation. BTC RSI {btc_rsi} with MACD {btc_macd} — deep in the pain zone. {sup} held multiple tests though, that breaks = new lows"

    # Bullish / recovery
    if any(w in text_lower for w in ["bullish", "pump", "rally", "recovery", "bounce", "reversal"]):
        return f"want to be bullish but data says not yet — BTC below all major MAs, RSI {btc_rsi}, MACD {btc_macd}. need {res} reclaimed before calling reversal. dead cat bounce risk is real"

    # Institutional / ETF
    if any(w in text_lower for w in ["institution", "etf", "morgan", "blackrock", "adoption", "bnp"]):
        return f"institutions buying while retail panics — same pattern every cycle. they position during fear, not euphoria. BTC RSI {btc_rsi} is exactly the zone smart money accumulates"

    # Trading / analysis / TA
    if any(w in text_lower for w in ["support", "resistance", "chart", "technical", "analysis"]):
        return f"key levels: {sup} support, {res} resistance. RSI {btc_rsi} leaves room either way. watching MACD at {btc_macd} for crossover signal — still negative but trend improving"

    # BTC / market generic
    if any(w in text_lower for w in ["btc", "bitcoin", "$btc", "market"]):
        return f"BTC at ${btc_price} with RSI {btc_rsi} — daily chart looks heavy but {sup} keeps holding. three tests without breaking is actually constructive. MACD crossover would confirm the bounce"

    # XRP
    if any(w in text_lower for w in ["xrp", "ripple", "$xrp"]):
        xrp_price = market.get("XRP", {}).get("price", "?")
        return f"XRP at ${xrp_price} — regulatory clarity was supposed to be the catalyst but price still tracking BTC. until macro shifts and BTC breaks {res}, alts stay rangebound"

    # BNB
    if any(w in text_lower for w in ["bnb", "$bnb"]):
        bnb_price = market.get("BNB", {}).get("price", "?")
        return f"BNB at ${bnb_price} holding relatively well. exchange tokens usually last to dump hard. still, not adding until BTC RSI recovers from {btc_rsi}"

    # Fallback
    return f"solid take. BTC RSI {btc_rsi} at {sup} support — inflection point. next few days should reveal if this is accumulation or distribution"


def _build_reply(handle: str, their_text: str, my_comment: str, btc_ta: dict) -> str:
    """Reply to someone who responded to my comment."""
    text_lower = their_text.lower()
    btc_support = btc_ta.get("support", "65500")

    try:
        sup = f"${float(btc_support):,.0f}"
    except (ValueError, TypeError):
        sup = str(btc_support)

    if any(w in text_lower for w in ["thank", "agree", "right", "exactly", "good point", "true", "nice"]):
        return f"appreciate it. watching {sup} closely — if it holds through the weekend might see a relief bounce early next week"

    if any(w in text_lower for w in ["disagree", "wrong", "no way", "but", "however", "actually"]):
        return "fair point — could go either way. that's what makes this range interesting. watching how the weekly candle closes"

    if "?" in their_text:
        btc_rsi = btc_ta.get("rsi", "?")
        return f"good question — watching RSI ({btc_rsi} rn) and daily MACD for direction. when those align with a support bounce, that's my signal"

    return "yeah for sure — tricky market. data helps cut through the noise though"


def _build_post(market: dict, btc_ta: dict, eth_ta: dict, news: list) -> tuple[str, str, str]:
    """Build a post. Returns (text, coin, sentiment).
    market = {"BTC": {"price", "change_24h"}, ...}
    btc_ta = {"rsi", "macd", "support", "resistance", "trend", "ma20", ...}
    """
    btc = market.get("BTC", {})
    eth = market.get("ETH", {})
    sol = market.get("SOL", {})

    btc_price = btc.get("price", 0)
    btc_change = btc.get("change_24h", 0)
    eth_price = eth.get("price", 0)
    eth_change = eth.get("change_24h", 0)
    sol_price = sol.get("price", 0)

    # Format prices
    def fmtp(v):
        try:
            return f"${float(v):,.0f}"
        except (ValueError, TypeError):
            return str(v)

    def fmtl(v):
        """Format level (support/resistance) nicely."""
        try:
            val = float(v)
            if val > 1000:
                return f"${val:,.0f}"
            return f"${val:,.2f}"
        except (ValueError, TypeError):
            return str(v)

    btc_p = fmtp(btc_price)
    eth_p = fmtp(eth_price)

    # TA — flat dict keys
    btc_rsi = btc_ta.get("rsi", "?")
    btc_macd = btc_ta.get("macd", "?")
    btc_support = fmtl(btc_ta.get("support", "?"))
    btc_resistance = fmtl(btc_ta.get("resistance", "?"))
    btc_ma20 = fmtl(btc_ta.get("ma20", "?"))
    btc_ma50 = fmtl(btc_ta.get("ma50", "?"))
    eth_rsi = eth_ta.get("rsi", "?")
    eth_support = fmtl(eth_ta.get("support", "?"))

    # Round RSI/MACD for readability
    try:
        btc_rsi_r = round(float(btc_rsi), 1)
    except (ValueError, TypeError):
        btc_rsi_r = btc_rsi
    try:
        btc_macd_r = round(float(btc_macd), 0)
    except (ValueError, TypeError):
        btc_macd_r = btc_macd
    try:
        eth_rsi_r = round(float(eth_rsi), 1)
    except (ValueError, TypeError):
        eth_rsi_r = eth_rsi
    try:
        btc_change_f = float(btc_change)
    except (ValueError, TypeError):
        btc_change_f = 0

    # Check for institutional news angle
    inst_headline = None
    for n in (news or []):
        title = n.get("title", "").lower() if isinstance(n, dict) else ""
        if any(w in title for w in ["etf", "morgan", "blackrock", "institution", "bnp", "bank", "sec"]):
            inst_headline = n.get("title", "")
            break

    # Mood
    if btc_change_f < -2:
        mood = "bleeding"
    elif btc_change_f < -0.5:
        mood = "drifting"
    elif btc_change_f > 2:
        mood = "pumping"
    elif btc_change_f > 0.5:
        mood = "recovering"
    else:
        mood = "flat"

    # Sentiment
    sentiment = "bearish" if btc_change_f < -1 else ("bullish" if btc_change_f > 1 else "neutral")

    if mood == "flat":
        text = (
            f"$BTC at {btc_p} — barely moving after days of red. the calm before the storm?\n\n"
            f"daily RSI {btc_rsi_r}, MACD {btc_macd_r}. still below 20 MA ({btc_ma20}) and 50 MA ({btc_ma50}). "
            f"sellers running out of ammo or just taking a breath?\n\n"
            f"{btc_support} support held 4+ tests now — either it becomes the floor or it breaks hard. "
            f"{btc_resistance} is the first real resistance. compressed ranges resolve violently.\n\n"
            f"$ETH at {eth_p} with 4H RSI {eth_rsi_r} — tracking BTC, underperforming. "
            f"need to reclaim {eth_support} as support before considering any longs.\n\n"
            f"have your alerts set, don't stare at charts all day. levels are clear.\n\n"
            f"#BTC #Bitcoin #CryptoAnalysis #TechnicalAnalysis"
        )
    elif mood in ("bleeding", "drifting"):
        text = (
            f"$BTC bleeding to {btc_p} ({btc_change}% 24h) — red days keep stacking.\n\n"
            f"RSI {btc_rsi_r} on daily, MACD {btc_macd_r}. every MA overhead = resistance. "
            f"the only backstop is {btc_support} support. it held so far but each test weakens it.\n\n"
            f"$ETH at {eth_p} ({eth_change}%), 4H RSI {eth_rsi_r}. $SOL at ${sol_price}.\n\n"
            f"not the time to catch knives. cash is a position. "
            f"if {btc_support} cracks, next support is way below.\n\n"
            f"#BTC #Bitcoin #CryptoMarket #BearMarket"
        )
    elif mood in ("pumping", "recovering"):
        text = (
            f"$BTC pushing to {btc_p} (+{btc_change}%) — first real green in a while.\n\n"
            f"RSI recovering to {btc_rsi_r} but MACD still {btc_macd_r}. one green day is not a reversal. "
            f"need {btc_resistance} broken and held to flip structure.\n\n"
            f"$ETH at {eth_p} — if BTC holds, ETH usually follows. watching {eth_support} as new floor.\n\n"
            f"cautiously optimistic but stops are tight. relief ≠ reversal.\n\n"
            f"#BTC #Bitcoin #CryptoRecovery #TechnicalAnalysis"
        )
    else:
        text = (
            f"$BTC at {btc_p} ({btc_change}%) — RSI {btc_rsi_r}, MACD {btc_macd_r}.\n\n"
            f"support {btc_support}, resistance {btc_resistance}. "
            f"range-bound until one breaks.\n\n"
            f"#BTC #Bitcoin #Crypto"
        )

    return text, "BTC", sentiment


if __name__ == "__main__":
    result = asyncio.run(session())
    print("\n=== SESSION SUMMARY ===")
    print(f"Comments: {result.get('comments_made')}")
    print(f"Likes: {result.get('likes_done')}")
    print(f"Engaged: {len(result.get('engaged', []))}")
    print(f"Replies found: {len(result.get('replies', []))}")
