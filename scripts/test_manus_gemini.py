"""Test image generation on Manus and Gemini."""
import asyncio
import base64
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright
import httpx

PROMPT = (
    "Create one original wide horizontal image (2:1 ratio) for a crypto market analysis post. "
    "The image should convey market tension and uncertainty. "
    "Style: semi-realistic, cinematic. Between anime and photography. "
    "Mood: serious, reserved, analytical. "
    "If a person is in the image — young guy with blonde/golden hair, sharp features, dark clothing. "
    "Context: BTC stuck at 65K support while institutions quietly accumulate. "
    "No text, no logos, no UI elements in the image."
)


async def test_manus(browser):
    """Try generating image on manus.im"""
    ctx = browser.contexts[0]
    page = None
    for p in ctx.pages:
        if 'manus.im' in str(p.url):
            page = p
            break

    if not page:
        print("MANUS: No tab found")
        return

    await page.bring_to_front()
    await asyncio.sleep(2)

    # Find composer
    print("MANUS: Looking for composer...")
    selectors = [
        "textarea",
        "[contenteditable='true']",
        "input[type='text']",
        "[role='textbox']",
    ]
    composer = None
    for sel in selectors:
        loc = page.locator(sel).last
        try:
            await loc.wait_for(state="visible", timeout=3000)
            composer = loc
            print(f"  Found: {sel}")
            break
        except Exception:
            continue

    if not composer:
        # Inspect what's on the page
        info = await page.evaluate("""() => {
            const els = document.querySelectorAll('textarea, [contenteditable], input, [role="textbox"]');
            return Array.from(els).map(el => ({
                tag: el.tagName,
                type: el.type || '',
                role: el.getAttribute('role') || '',
                contenteditable: el.contentEditable,
                placeholder: el.placeholder || '',
                cls: el.className.substring(0, 50),
                visible: el.offsetParent !== null
            }));
        }""")
        print(f"  Inputs found: {info}")
        return

    # Submit prompt
    print("MANUS: Submitting prompt...")
    await composer.click()
    await asyncio.sleep(0.5)
    try:
        await composer.fill(PROMPT)
    except Exception:
        await page.keyboard.insert_text(PROMPT)
    await asyncio.sleep(1)

    # Find send button
    send_selectors = [
        "button[type='submit']",
        "button:has-text('Send')",
        "button:has-text('Submit')",
        "button[aria-label*='Send']",
    ]
    for sel in send_selectors:
        btn = page.locator(sel).first
        try:
            await btn.wait_for(state="visible", timeout=2000)
            await btn.click()
            print(f"  Clicked: {sel}")
            break
        except Exception:
            continue
    else:
        # Try Enter
        await composer.press("Enter")
        print("  Pressed Enter")

    # Wait for image
    print("MANUS: Waiting for image generation (up to 120s)...")
    existing = await _get_large_images(page)

    for i in range(60):
        await asyncio.sleep(2)
        current = await _get_large_images(page)
        new_imgs = [img for img in current if img['src'] not in {e['src'] for e in existing}]
        if new_imgs:
            print(f"  New image found after {(i+1)*2}s: {new_imgs[0]['nw']}x{new_imgs[0]['nh']}")
            # Wait extra for render
            await asyncio.sleep(10)
            # Download via canvas
            current = await _get_large_images(page)
            new_imgs = [img for img in current if img['src'] not in {e['src'] for e in existing}]
            if new_imgs:
                await _download_image(page, new_imgs[0]['index'], 'data/generated_visuals/test_manus.png')
            return

    print("  Timeout — no image generated")


async def test_gemini(browser):
    """Try generating image on gemini.google.com"""
    ctx = browser.contexts[0]
    page = None
    for p in ctx.pages:
        if 'gemini.google.com' in str(p.url):
            page = p
            break

    if not page:
        print("GEMINI: No tab found")
        return

    await page.bring_to_front()
    await asyncio.sleep(2)

    # Find composer
    print("GEMINI: Looking for composer...")
    selectors = [
        "[contenteditable='true']",
        "textarea",
        "rich-textarea",
        ".ql-editor",
        "[role='textbox']",
    ]
    composer = None
    for sel in selectors:
        loc = page.locator(sel).last
        try:
            await loc.wait_for(state="visible", timeout=3000)
            composer = loc
            print(f"  Found: {sel}")
            break
        except Exception:
            continue

    if not composer:
        info = await page.evaluate("""() => {
            const els = document.querySelectorAll('textarea, [contenteditable], input, [role="textbox"], rich-textarea');
            return Array.from(els).map(el => ({
                tag: el.tagName,
                contenteditable: el.contentEditable,
                placeholder: el.placeholder || el.getAttribute('aria-label') || '',
                cls: el.className.substring(0, 50),
                visible: el.offsetParent !== null
            }));
        }""")
        print(f"  Inputs found: {info}")
        return

    print("GEMINI: Submitting prompt...")
    await composer.click()
    await asyncio.sleep(0.5)
    try:
        await composer.fill(PROMPT)
    except Exception:
        await page.keyboard.insert_text(PROMPT)
    await asyncio.sleep(1)

    # Send
    send_selectors = [
        "button[aria-label*='Send']",
        "button:has-text('Send')",
        "button.send-button",
        "[data-mat-icon-name='send']",
    ]
    for sel in send_selectors:
        btn = page.locator(sel).first
        try:
            await btn.wait_for(state="visible", timeout=2000)
            await btn.click()
            print(f"  Clicked: {sel}")
            break
        except Exception:
            continue
    else:
        await composer.press("Enter")
        print("  Pressed Enter")

    # Wait for image
    print("GEMINI: Waiting for image generation (up to 120s)...")
    existing = await _get_large_images(page)

    for i in range(60):
        await asyncio.sleep(2)
        current = await _get_large_images(page)
        new_imgs = [img for img in current if img['src'] not in {e['src'] for e in existing}]
        if new_imgs:
            print(f"  New image found after {(i+1)*2}s: {new_imgs[0]['nw']}x{new_imgs[0]['nh']}")
            await asyncio.sleep(10)
            current = await _get_large_images(page)
            new_imgs = [img for img in current if img['src'] not in {e['src'] for e in existing}]
            if new_imgs:
                await _download_image(page, new_imgs[0]['index'], 'data/generated_visuals/test_gemini.png')
            return

    print("  Timeout — no image generated")


async def _get_large_images(page):
    return await page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        const result = [];
        let idx = 0;
        for (const img of imgs) {
            const r = img.getBoundingClientRect();
            if (r.width > 200 && r.height > 150) {
                result.push({
                    src: img.src.substring(0, 100),
                    nw: img.naturalWidth,
                    nh: img.naturalHeight,
                    index: idx
                });
            }
            idx++;
        }
        return result;
    }""")


async def _download_image(page, img_index, output_path):
    """Download image — try canvas first, fallback to fetch, then screenshot."""
    # Method 1: canvas (works on same-origin)
    b64 = None
    try:
        b64 = await page.evaluate("""(idx) => {
            const imgs = document.querySelectorAll('img');
            const img = imgs[idx];
            if (!img) return null;
            const canvas = document.createElement('canvas');
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0);
            return canvas.toDataURL('image/png').split(',')[1];
        }""", img_index)
    except Exception:
        pass

    # Method 2: fetch with session cookies
    if not b64:
        try:
            b64 = await page.evaluate("""async (idx) => {
                const imgs = document.querySelectorAll('img');
                const img = imgs[idx];
                if (!img || !img.src) return null;
                const resp = await fetch(img.src);
                const blob = await resp.blob();
                return new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => resolve(reader.result.split(',')[1]);
                    reader.onerror = reject;
                    reader.readAsDataURL(blob);
                });
            }""", img_index)
        except Exception:
            pass

    # Method 3: element screenshot
    if not b64:
        try:
            imgs = page.locator("img")
            loc = imgs.nth(img_index)
            import os
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            await loc.screenshot(path=output_path)
            from PIL import Image
            img = Image.open(output_path)
            print(f"  Saved (screenshot): {output_path} — {img.size[0]}x{img.size[1]}")
            return
        except Exception as e:
            print(f"  All download methods failed: {e}")
            return

    if not b64:
        print("  Failed to get image data")
        return

    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    data = base64.b64decode(b64)
    with open(output_path, 'wb') as f:
        f.write(data)

    from PIL import Image
    img = Image.open(output_path)
    print(f"  Saved: {output_path} — {img.size[0]}x{img.size[1]} ({len(data)} bytes)")


async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get('http://local.adspower.net:50325/api/v1/browser/active', params={'serial_number': '1'})
        ws = r.json()['data']['ws']['puppeteer']

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(ws)

    print("=" * 40)
    print("Testing MANUS")
    print("=" * 40)
    await test_manus(browser)

    print()
    print("=" * 40)
    print("Testing GEMINI")
    print("=" * 40)
    await test_gemini(browser)

    await pw.stop()

asyncio.run(main())
