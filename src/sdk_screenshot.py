"""Screenshot and chart capture methods for BinanceSquareSDK.

Extracted as a mixin to keep sdk.py under 500 lines.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("bsq.sdk")


class SDKScreenshotMixin:
    """Screenshot methods mixed into BinanceSquareSDK."""

    async def take_screenshot(
        self,
        url: str,
        selector: str | None = None,
        crop: dict[str, int] | None = None,
        wait: int = 5,
    ) -> str:
        """Take a screenshot of a page or element via browser."""
        self._require_connection()
        page = self._page
        filepath = self._screenshot_output_path("capture")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(wait)
            await self._dismiss_cookie_banner()

            if selector:
                element = page.locator(selector).first
                await element.screenshot(path=filepath)
            elif crop:
                await page.screenshot(path=filepath, clip=crop)
            else:
                await page.screenshot(path=filepath)

            logger.info(f"Screenshot saved: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"take_screenshot: {e}, url={url}")
            raise SDKError(f"Screenshot failed: {e}") from e

    async def capture_targeted_screenshot(
        self,
        url: str,
        *,
        selectors: list[str] | None = None,
        text_anchors: list[str] | None = None,
        required_texts: list[str] | None = None,
        wait: int = 5,
    ) -> str:
        """Capture a meaningful fragment of a page instead of a fixed rectangle."""
        self._require_connection()
        page = self._page
        filepath = self._screenshot_output_path("targeted")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(wait)
            await page.evaluate("window.scrollTo(0, 0)")
            await self._dismiss_cookie_banner()
            await self._capture_current_view(
                filepath,
                selectors=selectors or [],
                text_anchors=text_anchors or [],
                required_texts=required_texts or [],
            )
            logger.info(f"Targeted screenshot saved: {filepath}")
            return filepath
        except Exception as exc:
            logger.error(f"capture_targeted_screenshot: {exc}, url={url}")
            raise SDKError(f"Targeted screenshot failed: {exc}") from exc

    async def screenshot_chart(self, symbol: str = "BTC_USDT", timeframe: str = "1D") -> str:
        """Capture a chart view from a dedicated desktop-style trade tab."""
        self._require_connection()
        filepath = self._screenshot_output_path(f"{symbol.replace('_', '')}_{timeframe}")
        url = f"https://www.binance.com/en/trade/{symbol}"
        pair_display = symbol.replace("_", "/")
        capture_page, owns_page = await self._select_chart_capture_page(symbol=symbol)
        original_page = self._page
        self._page = capture_page

        try:
            page_url = str(getattr(capture_page, "url", "") or "")
            if page_url != url and f"/trade/{symbol}?" not in page_url:
                await capture_page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                await asyncio.sleep(8)
            else:
                bring_to_front = getattr(capture_page, "bring_to_front", None)
                if callable(bring_to_front):
                    await bring_to_front()
                await asyncio.sleep(2)

            await capture_page.evaluate("window.scrollTo(0, 0)")
            await self._dismiss_cookie_banner()
            await self._prepare_chart_capture_page(capture_page)

            if timeframe != "1D":
                try:
                    tf_btn = capture_page.locator(f"text='{timeframe}'").first
                    await tf_btn.click(timeout=3_000)
                    await asyncio.sleep(3)
                except Exception:
                    logger.warning("screenshot_chart: timeframe selector not found for %s", timeframe)

            try:
                await self._capture_standardized_chart_view(
                    filepath,
                    pair_display=pair_display,
                    timeframe=timeframe,
                )
            except Exception as exc:
                logger.warning(
                    "screenshot_chart: standardized capture failed for %s — %s; trying targeted capture",
                    symbol,
                    exc,
                )
                try:
                    await self._capture_current_view(
                        filepath,
                        selectors=[
                            ".kline-container",
                            "[class*='showName']",
                            "[class*='symbol']",
                            "[class*='pair']",
                        ],
                        text_anchors=[
                            pair_display,
                            pair_display.replace("/", ""),
                            pair_display.split("/", 1)[0],
                            timeframe,
                        ],
                        required_texts=[pair_display],
                    )
                except Exception as targeted_exc:
                    logger.warning(
                        "screenshot_chart: targeted capture failed for %s — %s; falling back",
                        symbol,
                        targeted_exc,
                    )
                    await self._fallback_chart_capture(symbol=symbol, timeframe=timeframe, filepath=filepath)

            logger.info(f"Chart screenshot saved: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"screenshot_chart: {e}, symbol={symbol}")
            raise SDKError(f"Chart screenshot failed: {e}") from e
        finally:
            self._page = original_page
            if owns_page:
                try:
                    await capture_page.close()
                except Exception:
                    logger.debug("screenshot_chart: temporary capture page close skipped", exc_info=True)

    async def _select_chart_capture_page(self, *, symbol: str) -> tuple[Any, bool]:
        if not self._browser or not self._browser.contexts:
            return self._page, False

        context = self._browser.contexts[0]
        pages = list(context.pages)
        symbol_key = f"/trade/{symbol}"
        preferred: list[tuple[int, Any]] = []
        fallback: list[tuple[int, Any]] = []

        for page in pages:
            page_url = page.url or ""
            if "/en/trade/" not in page_url:
                continue
            try:
                width = int(await page.evaluate("() => window.innerWidth"))
            except Exception:
                width = 0
            bucket = preferred if symbol_key in page_url else fallback
            bucket.append((width, page))

        for bucket in (preferred, fallback):
            if not bucket:
                continue
            bucket.sort(key=lambda item: item[0], reverse=True)
            if bucket[0][0] >= 1280:
                return bucket[0][1], False

        try:
            page = await context.new_page()
            return page, True
        except Exception:
            logger.debug("screenshot_chart: failed to open dedicated capture page", exc_info=True)

        if preferred:
            preferred.sort(key=lambda item: item[0], reverse=True)
            return preferred[0][1], False
        if fallback:
            fallback.sort(key=lambda item: item[0], reverse=True)
            return fallback[0][1], False
        return self._page, False

    async def _prepare_chart_capture_page(self, page: Any) -> None:
        bring_to_front = getattr(page, "bring_to_front", None)
        if callable(bring_to_front):
            try:
                await bring_to_front()
            except Exception:
                logger.debug("screenshot_chart: bring_to_front skipped", exc_info=True)

        # Set viewport to 1920x1080 so price scale and dates fit
        try:
            await page.set_viewport_size({"width": 1920, "height": 1400})
            await asyncio.sleep(2)
        except Exception:
            logger.debug("screenshot_chart: set_viewport_size skipped", exc_info=True)

        await page.evaluate(
            """
            () => {
                if (document.body) {
                    document.body.style.background = '#0b0e11';
                }
            }
            """
        )
        await asyncio.sleep(2)

    async def _find_chart_anchor_boxes(
        self,
        *,
        pair_display: str,
        timeframe: str,
        chart_box: dict[str, float],
    ) -> list[dict[str, float]]:
        boxes = await self._collect_locator_boxes(
            [
                "[class*='showName']",
                "[class*='symbol']",
                "[class*='pair']",
            ]
        )
        boxes.extend(
            await self._collect_text_anchor_boxes(
                [pair_display, pair_display.replace("/", ""), timeframe, "Chart"]
            )
        )
        top_limit = float(chart_box["y"] - 180)
        bottom_limit = float(chart_box["y"] + 96)
        left_limit = float(chart_box["x"] - 48)
        right_limit = float(chart_box["x"] + chart_box["width"] + 48)
        return [
            box
            for box in boxes
            if box["y"] + box["height"] >= top_limit
            and box["y"] <= bottom_limit
            and box["x"] + box["width"] >= left_limit
            and box["x"] <= right_limit
        ]

    def _is_full_width_chart_layout(
        self,
        *,
        chart_box: dict[str, float],
        viewport: dict[str, int],
    ) -> bool:
        width = float(viewport["width"] or 1)
        return float(chart_box["x"]) <= 48 and float(chart_box["width"]) / width >= 0.82
    async def _capture_standardized_chart_view(
        self,
        filepath: str,
        *,
        pair_display: str,
        timeframe: str,
    ) -> None:
        # Wait for chart to render
        chart = self._page.locator(".kline-container").first
        await chart.wait_for(state="visible", timeout=20_000)

        # Simple full viewport screenshot — viewport is already set to 1920x1080
        await self._page.screenshot(path=filepath, full_page=False)

    async def _capture_current_view(
        self,
        filepath: str,
        *,
        selectors: list[str],
        text_anchors: list[str],
        required_texts: list[str],
    ) -> None:
        page_text = str(await self._page.locator("body").text_content() or "")
        lowered = page_text.lower()
        missing = [item for item in required_texts if item and item.lower() not in lowered]
        if missing:
            raise SDKError(f"Missing required text anchors on page: {missing}")

        boxes = await self._collect_locator_boxes(selectors)
        boxes.extend(await self._collect_text_anchor_boxes(text_anchors))
        if not boxes:
            raise SDKError("No visible anchors found for targeted screenshot")

        clip = await self._clip_from_boxes(boxes)
        await self._save_page_screenshot(filepath, clip=clip)

    async def _save_page_screenshot(
        self,
        filepath: str,
        *,
        clip: dict[str, float] | None = None,
    ) -> None:
        try:
            dpr_raw = await self._page.evaluate("window.devicePixelRatio || 1")
            dpr = float(dpr_raw) if dpr_raw else 1.0
            cdp_session = await self._page.context.new_cdp_session(self._page)
            payload: dict[str, object] = {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": False,
            }
            if clip is not None:
                payload["clip"] = {
                    "x": float(clip["x"]),
                    "y": float(clip["y"]),
                    "width": float(clip["width"]),
                    "height": float(clip["height"]),
                    "scale": dpr,
                }
            result = await cdp_session.send("Page.captureScreenshot", payload)
            import base64

            with open(filepath, "wb") as handle:
                handle.write(base64.b64decode(result["data"]))
            return
        except Exception:
            logger.debug("Falling back to Playwright screenshot capture", exc_info=True)

        screenshot_kwargs: dict[str, object] = {"path": filepath}
        if clip is not None:
            screenshot_kwargs["clip"] = clip
        await self._page.screenshot(**screenshot_kwargs)

    async def _collect_locator_boxes(self, selectors: list[str]) -> list[dict[str, float]]:
        boxes: list[dict[str, float]] = []
        for selector in selectors:
            if not selector:
                continue
            locator = self._page.locator(selector).first
            try:
                await locator.wait_for(state="visible", timeout=2_500)
                box = await locator.bounding_box()
            except Exception:
                continue
            if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                boxes.append(box)
        return boxes

    async def _collect_text_anchor_boxes(self, text_anchors: list[str]) -> list[dict[str, float]]:
        boxes: list[dict[str, float]] = []
        for anchor in text_anchors:
            if not anchor:
                continue
            locator = self._page.get_by_text(anchor, exact=False).first
            try:
                await locator.wait_for(state="visible", timeout=2_000)
                box = await locator.bounding_box()
            except Exception:
                continue
            if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                boxes.append(box)
        return boxes

    async def _clip_from_boxes(self, boxes: list[dict[str, float]], padding: int = 18) -> dict[str, float]:
        viewport = await self._viewport_size()
        left = max(min(box["x"] for box in boxes) - padding, 0)
        top = max(min(box["y"] for box in boxes) - padding, 0)
        right = min(max(box["x"] + box["width"] for box in boxes) + padding, viewport["width"])
        bottom = min(max(box["y"] + box["height"] for box in boxes) + padding, viewport["height"])
        return {
            "x": float(left),
            "y": float(top),
            "width": float(max(right - left, 1)),
            "height": float(max(bottom - top, 1)),
        }

    async def _chart_clip_from_standard_layout(
        self,
        *,
        chart_box: dict[str, float],
        header_boxes: list[dict[str, float]] | None = None,
    ) -> dict[str, float]:
        viewport = await self._viewport_size()
        bottom = min(int(chart_box["y"] + chart_box["height"]) + 10, viewport["height"])
        if bottom <= 0:
            raise SDKError("Standardized chart clip produced an invalid rectangle")

        if self._is_full_width_chart_layout(chart_box=chart_box, viewport=viewport):
            return {
                "x": 0.0,
                "y": 0.0,
                "width": float(max(viewport["width"], 1)),
                "height": float(max(bottom, 1)),
            }

        relevant_boxes = list(header_boxes or [])
        relevant_boxes.append(chart_box)
        left = max(int(chart_box["x"]) - 20, 0)
        top = max(int(min(box["y"] for box in relevant_boxes)) - 14, 0)
        right = min(int(chart_box["x"] + chart_box["width"]) + 20, viewport["width"])
        if right - left < 900:
            raise SDKError("Standardized chart clip is too narrow for posting")
        return {
            "x": float(left),
            "y": float(top),
            "width": float(max(right - left, 1)),
            "height": float(max(bottom - top, 1)),
        }

    async def _viewport_size(self) -> dict[str, int]:
        viewport = self._page.viewport_size
        if viewport is not None:
            return viewport
        return await self._page.evaluate(
            "() => ({ width: window.innerWidth, height: window.innerHeight })"
        )

    async def _dismiss_cookie_banner(self) -> None:
        try:
            await self._page.locator("button#onetrust-reject-all-handler").click(timeout=3_000)
            await asyncio.sleep(1)
        except Exception:
            return

    async def _fallback_chart_capture(self, *, symbol: str, timeframe: str, filepath: str) -> None:
        chart = self._page.locator(".kline-container").first
        await chart.wait_for(state="visible", timeout=20_000)
        chart_box = await chart.bounding_box()
        if not chart_box:
            raise SDKError("Chart container is visible but has no bounding box")

        clip = await self._chart_clip_from_standard_layout(chart_box=chart_box)
        await self._save_page_screenshot(filepath, clip=clip)

    def _screenshot_output_path(self, stem: str) -> str:
        import os
        import time

        screenshots_dir = os.path.join("data", "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        filename = f"{stem}_{int(time.time() * 1000)}.png"
        return os.path.abspath(os.path.join(screenshots_dir, filename))


class SDKError(Exception):
    """Raised when SDK operation fails."""
    pass

