"""Test comment flow: browse feed, open post, read it, comment, handle Follow popup."""
import asyncio
import random
from playwright.async_api import async_playwright


async def main():
    ws = "ws://127.0.0.1:56287/devtools/browser/1e7983e0-864e-4631-a2c3-da5ad930483e"

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(ws)
        context = browser.contexts[0]
        page = context.pages[0]

        # Go to Square
        await page.goto("https://www.binance.com/en/square", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # Click Recommended
        rec = page.locator("text=Recommended")
        if await rec.count() > 0:
            await rec.first.click()
            await asyncio.sleep(3)

        # Scroll to load posts
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(1.5)

        # Collect post links from page
        post_links = await page.locator('a[href*="/square/post/"]').all()
        seen = set()
        candidates = []

        for link in post_links:
            href = await link.get_attribute("href") or ""
            match = href.split("/post/")
            if len(match) < 2:
                continue
            post_id = match[1].split("?")[0].split("/")[0]
            if post_id in seen:
                continue
            seen.add(post_id)
            candidates.append(post_id)
            if len(candidates) >= 10:
                break

        print(f"Found {len(candidates)} post IDs")

        # Open each post, check if it's not ours, pick first good one
        target_id = None
        for pid in candidates:
            url = f"https://www.binance.com/en/square/post/{pid}"
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(4)

            # Check author
            page_text = await page.inner_text("body")
            if "aisama" in page_text[:500].lower():
                print(f"  Post {pid} — own post, skipping")
                continue

            # Check for enough text content
            if len(page_text) < 100:
                print(f"  Post {pid} — too short, skipping")
                continue

            # Check for spam
            text_lower = page_text.lower()
            if any(w in text_lower for w in ["giveaway", "airdrop", "copy trading", "gift"]):
                print(f"  Post {pid} — spam, skipping")
                continue

            target_id = pid
            break

        if not target_id:
            print("No suitable post found")
            return

        print(f"\nSelected post: {target_id}")

        # Read post content — filter out cookie/privacy banners
        paragraphs = await page.locator("p").all_inner_texts()
        filtered = [
            t.strip() for t in paragraphs
            if len(t.strip()) > 20
            and "cookies" not in t.lower()
            and "privacy" not in t.lower()[:30]
            and "switched off" not in t.lower()
            and "Sitemap" not in t
        ]
        post_content = " ".join(filtered[:5])
        print(f"Post content: {post_content[:300]}")

        # Generate comment based on content
        text_lower = post_content.lower()
        if "btc" in text_lower or "bitcoin" in text_lower:
            comment = "been watching btc closely too. the momentum shift is real but i want to see how it handles the next resistance before getting too excited"
        elif "eth" in text_lower or "ethereum" in text_lower:
            comment = "eth has been quiet for a while honestly. feels like something is building up but hard to tell which direction yet"
        elif "regulation" in text_lower or "sec" in text_lower:
            comment = "regulation clarity would be massive honestly. the uncertainty is what keeps most serious capital on the sidelines"
        elif "ai" in text_lower or "artificial" in text_lower:
            comment = "the ai narrative in crypto is interesting but most projects are just slapping ai on their name. curious which ones actually deliver"
        elif "defi" in text_lower:
            comment = "defi keeps evolving quietly while everyone chases memes. the real builders are still shipping"
        elif "bull" in text_lower or "pump" in text_lower:
            comment = "i get the optimism but every cycle teaches patience. would rather enter after confirmation than chase the fomo"
        elif "bear" in text_lower or "crash" in text_lower or "dump" in text_lower:
            comment = "fear phases are when the best entries happen but timing is everything. watching closely"
        elif "privacy" in text_lower or "private" in text_lower:
            comment = "privacy is one of those things nobody cares about until they need it. good to see projects actually building for it"
        elif "sol" in text_lower or "solana" in text_lower:
            comment = "solana ecosystem has been moving fast lately. curious how the network holds up when things really heat up"
        else:
            comment = "interesting take. not something i see discussed often but it makes sense when you think about it"

        print(f"\nComment: {comment}")

        # Scroll down to reply area
        reply_input = page.locator('input[placeholder="Post your reply"], input.rounded-10')
        await reply_input.first.scroll_into_view_if_needed()
        await asyncio.sleep(1)
        await reply_input.first.click()
        await asyncio.sleep(1)

        # Type with human delay
        await reply_input.type(comment, delay=45)
        await asyncio.sleep(2)

        # Click Reply button
        reply_btn = page.locator('button:has-text("Reply")').last
        await reply_btn.click()
        await asyncio.sleep(3)

        # Check for Follow & Reply popup
        follow_popup = page.locator("text=Follow to reply")
        if await follow_popup.count() > 0:
            print("Follow to reply popup detected! Clicking Follow & Reply...")
            follow_reply_btn = page.locator('button:has-text("Follow & Reply")').first
            await follow_reply_btn.click()
            await asyncio.sleep(3)
            # Comment was already sent with Follow — DO NOT write again
            print("Followed + commented via popup. Done.")
        else:
            print("Comment posted directly. Done.")


if __name__ == "__main__":
    asyncio.run(main())
