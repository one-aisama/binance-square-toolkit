"""Tests for CycleScheduler."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.accounts.manager import AccountConfig, PersonaConfig, LimitsConfig


def _make_settings():
    return {
        "cycle_interval_hours": [2, 4],
        "first_run_immediate": False,
        "bapi_base_url": "https://www.binance.com",
        "bapi_rate_limit_rpm": 30,
        "bapi_retry_attempts": 3,
        "bapi_retry_backoff_sec": 1.0,
        "adspower_base_url": "http://localhost:50325",
        "credential_max_age_hours": 12,
        "ai_provider": "anthropic",
        "ai_model": "test-model",
        "activity_delay_range_sec": [0, 0],
        "activity_skip_rate": 0.0,
        "activity_min_views_for_comment": 0,
    }


def _make_account():
    return AccountConfig(
        account_id="test_acc",
        persona_id="test_persona",
        adspower_profile_id="abc123",
        limits=LimitsConfig(),
        persona=PersonaConfig(
            id="test_persona",
            name="Test",
            topics=["defi"],
            style="analytical",
        ),
    )


def test_settings_loaded():
    settings = _make_settings()
    assert settings["cycle_interval_hours"] == [2, 4]
    assert settings["ai_provider"] == "anthropic"


def test_account_config_created():
    account = _make_account()
    assert account.account_id == "test_acc"
    assert account.persona is not None
    assert account.persona.style == "analytical"


def test_limits_defaults():
    limits = LimitsConfig()
    assert limits.posts_per_day == [3, 5]
    assert limits.likes_per_day == [30, 60]
    assert limits.min_interval_sec == 90
