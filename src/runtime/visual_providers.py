"""Visual provider registry — ChatGPT, Manus, Gemini with fallback chain.

Order: ChatGPT → Manus → Gemini. If one hits rate limit or fails, try next.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from src.runtime.agent_config import VisualConfig
from src.runtime.visual_prompt_builder import VisualPrompt
from src.session.web_visual import generate_image_from_web

logger = logging.getLogger("bsq.visual_providers")

# Provider URLs
PROVIDER_URLS = {
    "chatgpt": "https://chatgpt.com/",
    "manus": "https://manus.im/app",
    "gemini": "https://gemini.google.com/app",
}

# Fallback order
FALLBACK_CHAIN = ["chatgpt", "manus", "gemini"]


class VisualProvider(Protocol):
    async def generate(self, prompt: VisualPrompt) -> str:
        ...

    async def status(self) -> dict[str, Any]:
        ...


class WebVisualProvider:
    """Generate visuals through web AI services with fallback chain."""

    def __init__(self, sdk: Any, settings: VisualConfig):
        self._sdk = sdk
        self._settings = settings

    async def generate(self, prompt: VisualPrompt) -> str:
        browser = getattr(self._sdk, "_browser", None)
        if browser is None:
            raise RuntimeError("Visual provider requires an active browser session")

        errors = []
        for provider_name in FALLBACK_CHAIN:
            url = PROVIDER_URLS[provider_name]
            try:
                logger.info(f"Trying {provider_name} for image generation...")
                path = await generate_image_from_web(
                    browser=browser,
                    prompt=prompt.prompt,
                    output_dir=prompt.output_dir,
                    file_stem=f"{prompt.file_stem}_{provider_name}",
                    provider_url=url,
                    provider_name=provider_name,
                    timeout_sec=self._settings.prompt_timeout_sec,
                )
                logger.info(f"Image generated via {provider_name}: {path}")
                return path
            except Exception as exc:
                logger.warning(f"{provider_name} failed: {exc}")
                errors.append(f"{provider_name}: {exc}")
                continue

        raise RuntimeError(f"All visual providers failed: {'; '.join(errors)}")

    async def status(self) -> dict[str, Any]:
        return {
            "provider": "web_visual_chain",
            "chain": FALLBACK_CHAIN,
            "ready": getattr(self._sdk, "_browser", None) is not None,
        }


def build_visual_provider(sdk: Any, settings: VisualConfig) -> VisualProvider:
    return WebVisualProvider(sdk, settings)
