"""Test different methods to download ChatGPT image."""
import asyncio
import base64
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright
import httpx

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

    # Get image src
    src = await page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
            const r = img.getBoundingClientRect();
            if (r.width > 400 && r.height > 300) return img.src;
        }
        return null;
    }""")
    print(f'Image src: {src[:100]}...')

    # Method 1: fetch with blob -> base64
    print('\nMethod 1: fetch + blob + FileReader...')
    try:
        b64 = await page.evaluate("""async (url) => {
            const resp = await fetch(url);
            const blob = await resp.blob();
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result.split(',')[1]);
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            });
        }""", src)
        data = base64.b64decode(b64)
        with open('data/generated_visuals/test_method1.png', 'wb') as f:
            f.write(data)
        print(f'  Saved: {len(data)} bytes')
        from PIL import Image
        img = Image.open('data/generated_visuals/test_method1.png')
        print(f'  Size: {img.size[0]}x{img.size[1]}')
    except Exception as e:
        print(f'  Failed: {e}')

    # Method 2: fetch with arrayBuffer
    print('\nMethod 2: fetch + arrayBuffer...')
    try:
        b64 = await page.evaluate("""async (url) => {
            const resp = await fetch(url);
            const buf = await resp.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let binary = '';
            for (let i = 0; i < bytes.length; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            return btoa(binary);
        }""", src)
        data = base64.b64decode(b64)
        with open('data/generated_visuals/test_method2.png', 'wb') as f:
            f.write(data)
        print(f'  Saved: {len(data)} bytes')
        from PIL import Image
        img = Image.open('data/generated_visuals/test_method2.png')
        print(f'  Size: {img.size[0]}x{img.size[1]}')
    except Exception as e:
        print(f'  Failed: {e}')

    # Method 3: canvas drawImage toDataURL
    print('\nMethod 3: canvas drawImage...')
    try:
        b64 = await page.evaluate("""(url) => {
            return new Promise((resolve, reject) => {
                const img = new Image();
                img.crossOrigin = 'anonymous';
                img.onload = () => {
                    const canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    resolve(canvas.toDataURL('image/png').split(',')[1]);
                };
                img.onerror = reject;
                img.src = url;
            });
        }""", src)
        data = base64.b64decode(b64)
        with open('data/generated_visuals/test_method3.png', 'wb') as f:
            f.write(data)
        print(f'  Saved: {len(data)} bytes')
        from PIL import Image
        img = Image.open('data/generated_visuals/test_method3.png')
        print(f'  Size: {img.size[0]}x{img.size[1]}')
    except Exception as e:
        print(f'  Failed: {e}')

    # Method 4: screenshot of the largest image element
    print('\nMethod 4: element screenshot...')
    try:
        image_el = page.locator('img').last
        box = await image_el.bounding_box()
        if box and box['width'] > 400:
            await image_el.screenshot(path='data/generated_visuals/test_method4.png')
            from PIL import Image
            img = Image.open('data/generated_visuals/test_method4.png')
            print(f'  Size: {img.size[0]}x{img.size[1]}')
        else:
            print('  No large image found')
    except Exception as e:
        print(f'  Failed: {e}')

    await pw.stop()

asyncio.run(main())
