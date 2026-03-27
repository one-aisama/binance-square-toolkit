"""Browse feed, pick 4 interesting posts, like + comment + follow each."""

import asyncio
import json
from playwright.async_api import async_playwright


WS = "ws://127.0.0.1:59301/devtools/browser/21ee448d-68fb-41c7-b0bb-c9a53a55fd2f"

COMMENT_MAP = {
    "btc bitcoin halving": "btc price action has been interesting lately. curious where you see support if we get another dip",
    "eth ethereum layer l2": "eth ecosystem keeps growing but gas fees still push people to L2s. thats where the real action is imo",
    "defi yield lending staking": "defi yields have compressed a lot since last cycle. only the real protocols with actual revenue survive",
    "regulation sec fed trump policy": "regulation clarity would honestly be the biggest catalyst for crypto right now. uncertainty kills more than bad rules",
    "privacy security hack": "security should be priority number one but most projects treat it as an afterthought until they get exploited",
    "sol solana": "solana speed is unmatched but those outages still make people nervous. reliability matters more than tps",
    "ai artificial intelligence": "ai x crypto is interesting but 90 percent of these ai tokens have zero actual ai tech behind them. just buzzwords",
    "nft gaming metaverse": "nft space needed that correction. now only projects with actual utility are surviving which is healthy",
}
DEFAULT_COMMENT = "solid take. most people in crypto focus on short term noise but the ones who zoom out usually win"


def pick_comment(post_text: str) -> str:
    txt = post_text.lower()
    for keywords, comment in COMMENT_MAP.items():
        if any(w in txt for w in keywords.split()):
            return comment
    return DEFAULT_COMMENT


async def interact_with_post(page, post_id: str, comment_text: str):
    url = f"https://www.binance.com/en/square/post/{post_id}"
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(5)

    # Read author
    author = await page.evaluate("""() => {
        const els = document.querySelectorAll('a[href*="/square/profile/"]');
        for (const el of els) {
            const t = (el.innerText || '').trim();
            if (t && t.length > 1 && t.length < 40) return t;
        }
        return '?';
    }""")
    print(f"  @{author} (id={post_id})")

    # 1. Like
    try:
        like_btn = page.locator("div.thumb-up-button").first
        await like_btn.click(timeout=5000)
        await asyncio.sleep(2)
        print("  Liked")
    except Exception:
        print("  Like failed or already liked")

    # 2. Comment
    try:
        reply_input = page.locator('input[placeholder="Post your reply"]').first
        await reply_input.scroll_into_view_if_needed()
        await asyncio.sleep(2)
        await reply_input.click()
        await asyncio.sleep(1)
        await page.keyboard.type(comment_text, delay=60)
        await asyncio.sleep(2)

        reply_btn = page.locator('button:has-text("Reply")').first
        await reply_btn.click()
        await asyncio.sleep(3)

        # Check for "Follow & Reply" popup
        follow_reply = page.locator('button:has-text("Follow & Reply")').first
        try:
            await follow_reply.click(timeout=3000)
            await asyncio.sleep(3)
            print("  Commented (via Follow & Reply)")
            return  # Already followed
        except Exception:
            print("  Commented")
    except Exception as e:
        print(f"  Comment failed: {e}")

    # 3. Follow
    try:
        follow_btn = page.locator('button:has-text("Follow")').first
        await follow_btn.click(timeout=3000)
        await asyncio.sleep(2)
        print("  Followed")
    except Exception:
        print("  Already following")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(WS)
        context = browser.contexts[0]
        page = context.pages[0]

        # Browse recommended feed
        await page.goto("https://www.binance.com/en/square", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        rec_tab = page.locator("text=Recommended").first
        await rec_tab.click()
        await asyncio.sleep(3)

        for _ in range(6):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(2)

        # Collect post IDs
        post_ids = await page.evaluate("""() => {
            const ids = [];
            const seen = new Set();
            document.querySelectorAll('a[href*="/square/post/"]').forEach(a => {
                const m = a.href.match(/post\\/(\\d+)/);
                if (m && !seen.has(m[1])) { seen.add(m[1]); ids.push(m[1]); }
            });
            return ids;
        }""")
        print(f"Found {len(post_ids)} posts in feed")

        # Visit and interact with good posts
        done = 0
        for pid in post_ids:
            if done >= 4:
                break

            try:
                await page.goto(
                    f"https://www.binance.com/en/square/post/{pid}",
                    wait_until="domcontentloaded",
                    timeout=20000,
                )
                await asyncio.sleep(3)

                info = await page.evaluate("""() => {
                    let text = '';
                    document.querySelectorAll('p').forEach(el => {
                        const s = (el.innerText || '').trim();
                        if (s.length > 10) text += s + ' ';
                    });
                    let likes = 0;
                    const th = document.querySelector('.thumb-up-button .num span');
                    if (th) {
                        const r = th.innerText;
                        likes = r.includes('k') ? parseFloat(r)*1000 : parseInt(r)||0;
                    }
                    return { text: text.trim(), likes: likes };
                }""")

                txt = info["text"].lower()
                if (
                    len(info["text"]) < 50
                    or info["likes"] < 3
                    or "gift" in txt
                    or "giveaway" in txt
                    or "airdrop" in txt
                    or "copy trading" in txt
                ):
                    continue

                comment = pick_comment(info["text"])
                print(f"\n--- Post {done+1}/4 ---")
                await interact_with_post(page, pid, comment)
                done += 1

                delay = 15 + (done * 5)
                print(f"  Waiting {delay}s...")
                await asyncio.sleep(delay)

            except Exception as e:
                continue

        print(f"\n=== DONE: {done} posts interacted ===")


if __name__ == "__main__":
    asyncio.run(main())
