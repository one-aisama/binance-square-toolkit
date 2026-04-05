"""Tests for strategic bridge: directive loading and context finding."""

import json
from pathlib import Path

from src.operator.strategic_bridge import (
    _find_latest_context_summary,
    _load_directive,
    load_strategic_directive,
)


def test_load_directive_valid(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "data" / "runtime" / "example_macro"
    runtime_dir.mkdir(parents=True)
    directive = {
        "focus_summary": "SOL rotation looks real",
        "preferred_coins": ["SOL", "ETH"],
        "avoid_coins": ["DOGE"],
        "post_direction": "market_chart on SOL",
        "comment_direction": "macro threads",
        "skip_families": [],
        "tone": "analytical",
    }
    (runtime_dir / "strategic_directive.json").write_text(
        json.dumps(directive), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    result = _load_directive("example_macro")
    assert result is not None
    assert result["focus_summary"] == "SOL rotation looks real"
    assert result["preferred_coins"] == ["SOL", "ETH"]


def test_load_directive_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = _load_directive("nonexistent")
    assert result is None


def test_load_directive_invalid_json(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "data" / "runtime" / "example_macro"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "strategic_directive.json").write_text("not json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = _load_directive("example_macro")
    assert result is None


def test_load_directive_missing_focus(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "data" / "runtime" / "example_macro"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "strategic_directive.json").write_text(
        json.dumps({"preferred_coins": ["BTC"]}), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    result = _load_directive("example_macro")
    assert result is None


def test_find_latest_context_summary(tmp_path, monkeypatch):
    context_dir = tmp_path / "data" / "session_context"
    context_dir.mkdir(parents=True)
    (context_dir / "20260404T120000Z_example_macro.md").write_text("older", encoding="utf-8")
    (context_dir / "20260404T130000Z_example_macro.md").write_text("newer", encoding="utf-8")
    (context_dir / "20260404T130000Z_example_altcoin.md").write_text("other agent", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = _find_latest_context_summary("example_macro")
    assert result is not None
    assert "130000Z_example_macro" in result


def test_find_latest_context_summary_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = _find_latest_context_summary("example_macro")
    assert result is None


def test_load_strategic_directive_public_api(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "data" / "runtime" / "test"
    runtime_dir.mkdir(parents=True)
    directive = {"focus_summary": "test focus", "preferred_coins": []}
    (runtime_dir / "strategic_directive.json").write_text(
        json.dumps(directive), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    result = load_strategic_directive("test")
    assert result is not None
    assert result["focus_summary"] == "test focus"
