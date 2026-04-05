from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from src.runtime.agent_plan import AgentAction
from src.runtime.image_normalizer import is_landscape_ratio, normalize_image_to_landscape
from src.runtime.visual_pipeline import VisualPipeline


class DummySdk:
    def __init__(self):
        self._browser = MagicMock()

    async def screenshot_chart(self, symbol: str, timeframe: str) -> str:
        raise AssertionError("not used in this test")

    async def capture_targeted_screenshot(self, url: str, **kwargs) -> str:
        raise AssertionError("not used in this test")


def test_normalize_image_to_landscape_makes_wide_output(tmp_path):
    source = tmp_path / "tall.png"
    Image.new("RGB", (500, 1000), color=(30, 40, 50)).save(source)

    normalized_path = normalize_image_to_landscape(str(source))
    normalized = Image.open(normalized_path)

    assert normalized.width > normalized.height
    assert is_landscape_ratio(normalized.width, normalized.height)


@pytest.mark.asyncio
async def test_visual_pipeline_builds_reaction_card_without_active_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pipeline = VisualPipeline(DummySdk())
    action = AgentAction(
        action="post",
        priority=1,
        reason="publish reaction",
        text="the timeline gets loud faster than the evidence deserves\n\nthat alone is enough for me to slow down",
        visual_kind="market_visual",
        post_family="editorial_note",
        visual_title="Market note",
        visual_subtitle="A wider read on noisy conviction",
        visual_context="Built in test mode",
    )

    resolved = await pipeline.resolve(action)
    image = Image.open(resolved.path)

    assert resolved.kind == "market_visual"
    assert image.width > image.height
    assert is_landscape_ratio(image.width, image.height)


@pytest.mark.asyncio
async def test_visual_pipeline_routes_news_visuals_to_provider_when_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "agents" / "demo").mkdir(parents=True)
    (tmp_path / "agents" / "demo" / "visual_profile.md").write_text("- Clean editorial style", encoding="utf-8")
    (tmp_path / "config" / "active_agent.yaml").write_text(
        """
active_agent:
  agent_id: \"demo\"
  binance_username: \"demo\"
  profile_serial: \"1\"
  adspower_user_id: \"user\"
  persona_id: \"demo\"
  agent_dir: \"agents/demo\"
  account_config_path: \"config/accounts/demo.yaml\"
  visual:
    enabled: true
    provider: \"chatgpt_web\"
    profile_path: \"agents/demo/visual_profile.md\"
""".strip(),
        encoding="utf-8",
    )
    source = tmp_path / "provider.png"
    Image.new("RGB", (1400, 780), color=(40, 50, 60)).save(source)
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=str(source.resolve()))

    with patch("src.runtime.visual_pipeline.build_visual_provider", return_value=provider):
        pipeline = VisualPipeline(DummySdk())

    action = AgentAction(
        action="post",
        priority=1,
        reason="publish news",
        text="headline risk is loud but the second-order move matters more",
        visual_kind="news_visual",
        post_family="news_reaction",
        visual_title="ETF flows wobble again",
        visual_subtitle="Liquidity stayed selective",
        visual_context="Test context",
    )

    resolved = await pipeline.resolve(action)

    provider.generate.assert_awaited_once()
    assert resolved.kind == "news_visual"
    assert Path(resolved.path).exists()


@pytest.mark.asyncio
async def test_visual_pipeline_keeps_chart_capture_raw(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "chart.png"
    Image.new("RGB", (1534, 1081), color=(15, 20, 30)).save(source)

    sdk = DummySdk()
    sdk.screenshot_chart = AsyncMock(return_value=str(source.resolve()))
    pipeline = VisualPipeline(sdk)
    action = AgentAction(
        action="post",
        priority=1,
        reason="publish chart take",
        text="market structure still matters more than one fast candle",
        chart_image=True,
        chart_symbol="BTC_USDT",
        chart_timeframe="4H",
    )

    resolved = await pipeline.resolve(action)

    assert resolved.kind == "chart_capture"
    assert resolved.path == str(source.resolve())
    assert not resolved.path.endswith("_wide.png")

@pytest.mark.asyncio
async def test_visual_pipeline_maps_legacy_news_card_to_ai_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "agents" / "demo").mkdir(parents=True)
    (tmp_path / "agents" / "demo" / "visual_profile.md").write_text("- Clean editorial style", encoding="utf-8")
    (tmp_path / "config" / "active_agent.yaml").write_text(
        """
active_agent:
  agent_id: \"demo\"
  binance_username: \"demo\"
  profile_serial: \"1\"
  adspower_user_id: \"user\"
  persona_id: \"demo\"
  agent_dir: \"agents/demo\"
  account_config_path: \"config/accounts/demo.yaml\"
  visual:
    enabled: true
    provider: \"chatgpt_web\"
    profile_path: \"agents/demo/visual_profile.md\"
""".strip(),
        encoding="utf-8",
    )
    source = tmp_path / "provider.png"
    Image.new("RGB", (1400, 780), color=(40, 50, 60)).save(source)
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=str(source.resolve()))

    with patch("src.runtime.visual_pipeline.build_visual_provider", return_value=provider):
        pipeline = VisualPipeline(DummySdk())

    action = AgentAction(
        action="post",
        priority=1,
        reason="publish news",
        text="the headline is loud but the second order move matters more",
        visual_kind="news_card",
        post_family="news_reaction",
        visual_title="ETF flows wobble again",
        visual_subtitle="Liquidity stayed selective",
        visual_context="Test context",
    )

    resolved = await pipeline.resolve(action)

    provider.generate.assert_awaited_once()
    assert resolved.kind == "news_card"
    assert Path(resolved.path).exists()


@pytest.mark.asyncio
async def test_visual_pipeline_keeps_ai_generated_visual_raw(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "agents" / "demo").mkdir(parents=True)
    (tmp_path / "agents" / "demo" / "visual_profile.md").write_text("- Clean editorial style", encoding="utf-8")
    (tmp_path / "config" / "active_agent.yaml").write_text(
        """
active_agent:
  agent_id: \"demo\"
  binance_username: \"demo\"
  profile_serial: \"1\"
  adspower_user_id: \"user\"
  persona_id: \"demo\"
  agent_dir: \"agents/demo\"
  account_config_path: \"config/accounts/demo.yaml\"
  visual:
    enabled: true
    provider: \"chatgpt_web\"
    profile_path: \"agents/demo/visual_profile.md\"
""".strip(),
        encoding="utf-8",
    )
    source = tmp_path / "provider.png"
    Image.new("RGB", (1536, 1024), color=(40, 50, 60)).save(source)
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=str(source.resolve()))

    with patch("src.runtime.visual_pipeline.build_visual_provider", return_value=provider):
        pipeline = VisualPipeline(DummySdk())

    action = AgentAction(
        action="post",
        priority=1,
        reason="publish news",
        text="the headline is loud but the second order move matters more",
        visual_kind="news_visual",
        post_family="news_reaction",
        visual_title="ETF flows wobble again",
        visual_subtitle="Liquidity stayed selective",
        visual_context="Test context",
    )

    resolved = await pipeline.resolve(action)

    assert resolved.path == str(source.resolve())
    assert not resolved.path.endswith("_wide.png")
