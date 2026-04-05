from __future__ import annotations

import hashlib
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from src.runtime.agent_config import ActiveAgentConfig, load_active_agent
from src.runtime.agent_plan import AgentAction
from src.runtime.image_normalizer import normalize_image_to_landscape
from src.runtime.visual_prompt_builder import AI_VISUAL_KINDS, build_visual_prompt, normalize_visual_kind
from src.runtime.visual_providers import build_visual_provider

GENERATED_DIR = Path("data/generated_visuals")
CARD_SIZE = (1600, 800)
PADDING = 80
FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/calibri.ttf",
]

STYLE_MAP: dict[str, dict[str, Any]] = {
    "market_visual": {
        "background": (11, 16, 29),
        "panel": (22, 31, 56),
        "accent": (72, 198, 149),
        "label": "MARKET",
    },
    "news_visual": {
        "background": (11, 16, 29),
        "panel": (22, 31, 56),
        "accent": (255, 205, 62),
        "label": "NEWS",
    },
    "meme_visual": {
        "background": (26, 19, 24),
        "panel": (54, 31, 42),
        "accent": (255, 143, 97),
        "label": "MEME",
    },
    "personal_visual": {
        "background": (18, 20, 31),
        "panel": (31, 37, 58),
        "accent": (180, 160, 220),
        "label": "PERSONAL",
    },
    "article_cover": {
        "background": (14, 14, 22),
        "panel": (28, 28, 44),
        "accent": (100, 200, 255),
        "label": "ARTICLE",
    },
}


@dataclass(frozen=True)
class ResolvedVisual:
    path: str
    kind: str
    signature: str


class VisualPipeline:
    """Resolve or build the image that accompanies a post."""

    def __init__(self, sdk: Any, config_path: str = "config/active_agent.yaml"):
        self._sdk = sdk
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        self._agent = self._load_agent_config(config_path)
        self._provider = self._load_provider()

    async def resolve(self, action: AgentAction) -> ResolvedVisual | None:
        if action.image_path:
            path = normalize_image_to_landscape(action.image_path)
            return ResolvedVisual(path=path, kind="image", signature=self._signature("image", path))

        if action.visual_kind:
            return await self._resolve_visual_kind(action)

        if action.chart_image:
            path = await self._sdk.screenshot_chart(action.chart_symbol, action.chart_timeframe)
            return ResolvedVisual(
                path=path,
                kind="chart_capture",
                signature=self._signature("chart_capture", action.chart_symbol, action.chart_timeframe),
            )
        return None

    async def _resolve_visual_kind(self, action: AgentAction) -> ResolvedVisual:
        requested_kind = str(action.visual_kind or "").lower()
        normalized_kind = normalize_visual_kind(requested_kind)
        if normalized_kind == "chart_capture":
            path = await self._resolve_chart_capture(action)
        elif normalized_kind == "page_capture":
            path = await self._resolve_page_capture(action)
        elif normalized_kind in AI_VISUAL_KINDS:
            path = await self._resolve_ai_visual(action, normalized_kind)
        else:
            raise ValueError(f"Unsupported visual_kind: {action.visual_kind}")

        resolved_path = self._finalize_path(path, normalized_kind)
        return ResolvedVisual(
            path=resolved_path,
            kind=requested_kind or normalized_kind,
            signature=self._signature(requested_kind or normalized_kind, action.text or "", action.visual_title or ""),
        )

    async def _resolve_chart_capture(self, action: AgentAction) -> str:
        if action.capture_url:
            return await self._sdk.capture_targeted_screenshot(
                action.capture_url,
                selectors=action.capture_selectors,
                text_anchors=action.capture_text_anchors,
                required_texts=action.capture_required_texts,
                wait=8,
            )
        if not action.chart_symbol:
            raise ValueError("chart_symbol is required for chart_capture visuals")
        return await self._sdk.screenshot_chart(action.chart_symbol, action.chart_timeframe)

    async def _resolve_page_capture(self, action: AgentAction) -> str:
        if not action.capture_url:
            raise ValueError("capture_url is required for page_capture visuals")
        return await self._sdk.capture_targeted_screenshot(
            action.capture_url,
            selectors=action.capture_selectors,
            text_anchors=action.capture_text_anchors,
            required_texts=action.capture_required_texts,
            wait=6,
        )

    async def _resolve_ai_visual(self, action: AgentAction, kind: str) -> str:
        if self._agent is None or self._provider is None:
            return self._build_text_card(action, kind)
        prompt = build_visual_prompt(
            action,
            agent_id=self._agent.agent_id,
            agent_dir=self._agent.agent_dir,
            settings=self._agent.visual,
        )
        return await self._provider.generate(prompt)

    def _finalize_path(self, path: str, normalized_kind: str) -> str:
        if normalized_kind == "chart_capture" or normalized_kind in AI_VISUAL_KINDS:
            return path
        return normalize_image_to_landscape(path)

    def _load_agent_config(self, config_path: str) -> ActiveAgentConfig | None:
        try:
            return load_active_agent(config_path)
        except FileNotFoundError:
            return None

    def _load_provider(self):
        if self._agent is None or not self._agent.visual.enabled:
            return None
        return build_visual_provider(self._sdk, self._agent.visual)

    def _build_text_card(self, action: AgentAction, kind: str) -> str:
        style = STYLE_MAP[kind]
        image = Image.new("RGB", CARD_SIZE, style["background"])
        draw = ImageDraw.Draw(image)
        title_font = self._load_font(44)
        body_font = self._load_font(26)
        small_font = self._load_font(18)

        panel_box = (60, 60, CARD_SIZE[0] - 60, CARD_SIZE[1] - 60)
        draw.rounded_rectangle(panel_box, radius=36, fill=style["panel"])
        draw.rounded_rectangle((86, 86, 360, 126), radius=16, fill=style["accent"])
        draw.text((112, 96), style["label"], fill=(14, 18, 29), font=small_font)

        title = action.visual_title or self._fallback_title(action)
        subtitle = action.visual_subtitle or action.text or ""
        context = action.visual_context or action.reason or ""

        draw.multiline_text(
            (PADDING + 10, 180),
            self._wrap_text(title, 32),
            fill=(245, 247, 252),
            font=title_font,
            spacing=12,
        )
        draw.multiline_text(
            (PADDING + 10, 360),
            self._wrap_text(subtitle, 70),
            fill=(210, 216, 231),
            font=body_font,
            spacing=10,
        )
        draw.multiline_text(
            (PADDING + 10, 690),
            self._wrap_text(context, 84),
            fill=style["accent"],
            font=small_font,
            spacing=8,
        )

        output_path = GENERATED_DIR / f"{kind}_{self._signature(title, subtitle, context)}.png"
        image.save(output_path)
        return str(output_path.resolve())

    def _load_font(self, size: int) -> ImageFont.ImageFont:
        for candidate in FONT_CANDIDATES:
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _fallback_title(self, action: AgentAction) -> str:
        text = (action.text or "").split("\n\n", 1)[0].strip()
        return text[:120] or "Market note"

    def _wrap_text(self, text: str, width: int) -> str:
        cleaned = " ".join(str(text or "").split())
        return textwrap.fill(cleaned, width=width)

    def _signature(self, *parts: object) -> str:
        payload = "|".join(str(part or "") for part in parts)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


