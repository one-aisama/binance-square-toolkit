"""Web-based visual generation — ChatGPT, Manus, Gemini.

All three work the same way: open tab, find composer, submit prompt,
wait for image, download via fetch or canvas.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("bsq.web_visual")

# Provider-specific composer selectors (ordered by priority)
COMPOSER_SELECTORS = {
    "chatgpt": ["#prompt-textarea", "[contenteditable='true']", "textarea"],
    "manus": ["[contenteditable='true']", "textarea", "[role='textbox']"],
    "gemini": ["rich-textarea", "[contenteditable='true']", "textarea", "[role='textbox']"],
}

# Provider-specific send button selectors
SEND_SELECTORS = {
    "chatgpt": ["button[data-testid='send-button']", "button[aria-label*='Send']"],
    "manus": ["button[type='submit']", "button:has-text('Send')"],
    "gemini": ["button[aria-label*='Send']", "button.send-button"],
}


async def generate_image_from_web(
    *,
    browser: Any,
    prompt: str,
    output_dir: str,
    file_stem: str,
    provider_url: str,
    provider_name: str,
    timeout_sec: int = 180,
    render_wait_sec: int = 60,
) -> str:
    """Generate image via web AI service. Works for ChatGPT, Manus, Gemini."""
    context = browser.contexts[0] if getattr(browser, "contexts", None) else None
    if context is None:
        raise RuntimeError(f"{provider_name}: no browser context available")

    page = await _find_or_open_page(context, provider_url)
    await _bring_to_front(page)
    await asyncio.sleep(2)

    composer = await _find_composer(page, provider_name)
    if composer is None:
        # Check login
        login = page.locator("button:has-text('Log in'), a:has-text('Log in'), button:has-text('Sign up'), button:has-text('Sign in')").first
        try:
            await login.wait_for(state="visible", timeout=2_000)
            raise RuntimeError(f"{provider_name}: NOT logged in — login page detected")
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError(f"{provider_name}: composer not found, page may not have loaded")

    existing_sources = await _collect_image_sources(page)
    await _submit_prompt(page, composer, prompt, provider_name)

    logger.info(f"{provider_name}: waiting for image generation (up to {timeout_sec}s)...")
    image_locator, img_info = await _wait_for_new_image(page, existing_sources, timeout_sec=timeout_sec)

    # Wait for full render
    logger.info(f"{provider_name}: image found, waiting {render_wait_sec}s for full render...")
    await asyncio.sleep(render_wait_sec)

    # Download
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filepath = output_path / f"{file_stem}.png"

    raw = await _download_image(page, image_locator)
    if len(raw) < 10_000:
        raise RuntimeError(f"{provider_name}: downloaded image too small ({len(raw)} bytes)")

    with open(str(filepath), "wb") as f:
        f.write(raw)

    # Validate
    from PIL import Image
    try:
        img = Image.open(str(filepath))
        img.verify()
    except Exception as exc:
        filepath.unlink(missing_ok=True)
        raise RuntimeError(f"{provider_name}: image corrupted: {exc}") from exc

    img = Image.open(str(filepath))
    if img.width < 512 or img.height < 256:
        filepath.unlink(missing_ok=True)
        raise RuntimeError(f"{provider_name}: image too small: {img.width}x{img.height}")

    logger.info(f"{provider_name}: saved {img.width}x{img.height} ({len(raw)} bytes)")
    return str(filepath.resolve())


async def _find_or_open_page(context: Any, url: str):
    for page in list(getattr(context, "pages", [])):
        if url.rstrip("/") in str(getattr(page, "url", "") or ""):
            return page
    page = await context.new_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    await asyncio.sleep(3)
    return page


async def _bring_to_front(page: Any):
    fn = getattr(page, "bring_to_front", None)
    if callable(fn):
        try:
            await fn()
        except Exception as exc:
            logger.debug("bring_to_front skipped: %s", exc)


async def _find_composer(page: Any, provider_name: str):
    selectors = COMPOSER_SELECTORS.get(provider_name, COMPOSER_SELECTORS["chatgpt"])
    for sel in selectors:
        loc = page.locator(sel).last
        try:
            await loc.wait_for(state="visible", timeout=5_000)
            return loc
        except Exception:
            continue
    return None


async def _submit_prompt(page: Any, composer: Any, prompt: str, provider_name: str):
    await composer.click()
    await asyncio.sleep(0.5)
    try:
        await composer.fill(prompt)
    except Exception:
        try:
            await page.keyboard.insert_text(prompt)
        except Exception:
            await page.keyboard.type(prompt, delay=5)
    await asyncio.sleep(1)

    # Try send button
    selectors = SEND_SELECTORS.get(provider_name, SEND_SELECTORS["chatgpt"])
    for sel in selectors:
        btn = page.locator(sel).first
        try:
            await btn.wait_for(state="visible", timeout=2_000)
            await btn.click()
            logger.info(f"{provider_name}: prompt submitted via {sel}")
            return
        except Exception:
            continue
    # Fallback: Enter
    await composer.press("Enter")
    logger.info(f"{provider_name}: prompt submitted via Enter")


async def _collect_image_sources(page: Any) -> set[str]:
    sources = await page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        const srcs = new Set();
        for (const img of imgs) {
            const r = img.getBoundingClientRect();
            if (r.width > 200 && r.height > 150 && img.src) srcs.add(img.src);
        }
        return Array.from(srcs);
    }""")
    return set(sources)


async def _wait_for_new_image(page: Any, existing: set[str], *, timeout_sec: int):
    deadline = asyncio.get_running_loop().time() + timeout_sec
    while asyncio.get_running_loop().time() < deadline:
        images = page.locator("img")
        count = await images.count()
        best = None
        best_area = 0.0
        for i in range(count):
            loc = images.nth(i)
            try:
                src = str(await loc.get_attribute("src") or "")
                box = await loc.bounding_box()
                if not src or src in existing or box is None:
                    continue
                natural = await loc.evaluate("el => ({w: el.naturalWidth, h: el.naturalHeight, c: el.complete})")
                if not natural.get("c") or natural.get("w", 0) < 400:
                    continue
                area = box["width"] * box["height"]
                if area > best_area:
                    best = (loc, {"src": src, "nw": natural["w"], "nh": natural["h"]})
                    best_area = area
            except Exception:
                continue
        if best:
            return best
        await asyncio.sleep(3)
    raise RuntimeError("Image generation timed out")


async def _download_image(page: Any, image_locator: Any) -> bytes:
    """Download image bytes — try canvas, then fetch, then screenshot."""
    handle = await image_locator.element_handle()

    # Method 1: canvas drawImage
    try:
        b64 = await page.evaluate("""(el) => {
            const canvas = document.createElement('canvas');
            canvas.width = el.naturalWidth;
            canvas.height = el.naturalHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(el, 0, 0);
            return canvas.toDataURL('image/png').split(',')[1];
        }""", handle)
        if b64:
            return base64.b64decode(b64)
    except Exception as exc:
        logger.debug("canvas download failed: %s", exc)

    # Method 2: fetch with cookies
    try:
        b64 = await page.evaluate("""async (el) => {
            if (!el.src) return null;
            const resp = await fetch(el.src);
            const blob = await resp.blob();
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result.split(',')[1]);
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            });
        }""", handle)
        if b64:
            return base64.b64decode(b64)
    except Exception as exc:
        logger.debug("fetch download failed: %s", exc)

    # Method 3: element screenshot (worst quality but always works)
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    await image_locator.screenshot(path=tmp.name)
    with open(tmp.name, "rb") as f:
        data = f.read()
    Path(tmp.name).unlink(missing_ok=True)
    return data
