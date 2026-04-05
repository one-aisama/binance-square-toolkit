"""Inspect large images on ChatGPT page to debug download issue."""
import asyncio
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright
import httpx

JS = """() => {
    const imgs = document.querySelectorAll('img');
    const result = [];
    for (const img of imgs) {
        const r = img.getBoundingClientRect();
        if (r.width > 200 && r.height > 200) {
            result.push({
                src: img.src.substring(0, 150),
                nw: img.naturalWidth,
                nh: img.naturalHeight,
                dw: Math.round(r.width),
                dh: Math.round(r.height),
                alt: (img.alt || '').substring(0, 50),
                complete: img.complete,
                srcset: (img.srcset || '').substring(0, 100)
            });
        }
    }
    return result;
}"""

async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get('http://local.adspower.net:50325/api/v1/browser/active', params={'serial_number': '1'})
        ws = r.json()['data']['ws']['puppeteer']

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(ws)
    ctx = browser.contexts[0]

    page = None
    for p in ctx.pages:
        if 'chatgpt.com' in str(p.url):
            page = p
            break

    if not page:
        print('No ChatGPT page')
        await pw.stop()
        return

    images = await page.evaluate(JS)

    print(f'Large images ({len(images)}):')
    for i, img in enumerate(images):
        print(f'  [{i}] natural: {img["nw"]}x{img["nh"]}, display: {img["dw"]}x{img["dh"]}, complete: {img["complete"]}')
        print(f'      src: {img["src"]}')
        if img["srcset"]:
            print(f'      srcset: {img["srcset"]}')

    await pw.stop()

asyncio.run(main())
