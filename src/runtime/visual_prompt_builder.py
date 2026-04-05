from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from src.runtime.agent_config import VisualConfig
from src.runtime.agent_plan import AgentAction

LEGACY_VISUAL_KIND_MAP = {
    "news_card": "news_visual",
    "reaction_card": "personal_visual",
}
AI_VISUAL_KINDS = {"market_visual", "news_visual", "meme_visual", "personal_visual", "article_cover"}

_KIND_GUIDANCE = {
    "market_visual": "Create an atmospheric illustration for a crypto market analysis post. The image should convey market structure, positioning, or price action mood — not a literal chart.",
    "news_visual": "Create an editorial illustration for a crypto news post. The image should feel timely and relevant to the event described, with journalistic energy.",
    "meme_visual": "Create a humorous or ironic illustration for a crypto shitpost. The image should be funny, relatable, or provocative — matching internet humor culture.",
    "personal_visual": "Create a lifestyle illustration for a personal post. The image should feel authentic, casual, and human — like a real moment from someone's day.",
    "article_cover": "Create a cover illustration for a long-form crypto article. The image should be bold, editorial, and work as a standalone visual at any size.",
}

_HARD_RULES = (
    "Hard rules: one single wide horizontal image with 2:1 aspect ratio (width is twice the height), "
    "no text in the image, no captions, no logos, no exchange UI, no screenshots, "
    "no split panels, no watermarks, no extra frames, no collage."
)


@dataclass(frozen=True)
class VisualPrompt:
    kind: str
    prompt: str
    output_dir: str
    file_stem: str


def normalize_visual_kind(kind: str | None) -> str:
    normalized = str(kind or "").lower()
    return LEGACY_VISUAL_KIND_MAP.get(normalized, normalized)


def build_visual_prompt(
    action: AgentAction,
    *,
    agent_id: str,
    agent_dir: str,
    settings: VisualConfig,
) -> VisualPrompt:
    kind = normalize_visual_kind(action.visual_kind)
    profile_text = _load_visual_profile(agent_dir=agent_dir, settings=settings)
    prompt = _compose_prompt(action=action, kind=kind, agent_id=agent_id, profile_text=profile_text)
    file_stem = f"{kind}_{_signature(agent_id, action.text or '', action.visual_title or '', action.source_url or '')}"
    return VisualPrompt(kind=kind, prompt=prompt, output_dir=settings.output_dir, file_stem=file_stem)


def _load_visual_profile(*, agent_dir: str, settings: VisualConfig) -> str:
    path = Path(settings.profile_path) if settings.profile_path else Path(agent_dir) / "visual_profile.md"
    if not path.exists():
        raise FileNotFoundError(f"Visual profile not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def _compose_prompt(
    *,
    action: AgentAction,
    kind: str,
    agent_id: str,
    profile_text: str,
) -> str:
    sections = [
        f"Create one original visual for Binance Square agent {agent_id}.",
        _KIND_GUIDANCE.get(kind, "Create one clean editorial illustration for the post below."),
        "Format: wide horizontal composition suitable for a Binance Square feed image.",
        _HARD_RULES,
        f"Agent visual profile:\n{profile_text}",
        _post_material(action),
    ]
    return "\n\n".join(section for section in sections if section.strip())


def _post_material(action: AgentAction) -> str:
    lines = ["Post material:"]
    if action.visual_title:
        lines.append(f"Title: {action.visual_title}")
    if action.visual_subtitle:
        lines.append(f"Subtitle: {action.visual_subtitle}")
    if action.visual_context:
        lines.append(f"Context: {action.visual_context}")
    if action.post_family:
        lines.append(f"Post family: {action.post_family}")
    if action.text:
        lines.append(f"Post text: {action.text}")
    return "\n".join(lines)


def _signature(*parts: object) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
