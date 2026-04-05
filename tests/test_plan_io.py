"""Tests for plan I/O: save, load, update, validate pending plans."""

import json

import pytest

from src.runtime.agent_plan import AgentAction, AgentPlan
from src.runtime.plan_io import (
    delete_pending_plan,
    load_pending_plan,
    load_plan_for_execution,
    save_pending_plan,
    update_pending_plan,
)


class FakeDirective:
    stage = "analytical_builder"
    target_comments = 3
    target_likes = 5
    target_posts = 1
    target_follows = 1


@pytest.fixture
def plan_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("src.runtime.plan_io.RUNTIME_DIR", tmp_path)
    return tmp_path


def _make_plan() -> AgentPlan:
    return AgentPlan(actions=[
        AgentAction(action="comment", priority=1, reason="test", target="111", target_text="some post text"),
        AgentAction(action="like", priority=2, reason="test", target="222"),
        AgentAction(action="post", priority=3, reason="test", brief_context="angle: macro\ncoin: BTC"),
    ])


def test_save_and_load_pending_plan(plan_dir):
    plan = _make_plan()
    path = save_pending_plan(
        agent_id="example_macro",
        plan=plan,
        directive=FakeDirective(),
        context_files={"json": "ctx.json", "md": "ctx.md"},
    )

    assert "example_macro" in path
    loaded = load_pending_plan("example_macro")
    assert loaded["agent_id"] == "example_macro"
    assert len(loaded["actions"]) == 3
    assert loaded["directive"]["stage"] == "analytical_builder"


def test_load_nonexistent_raises(plan_dir):
    with pytest.raises(FileNotFoundError):
        load_pending_plan("nonexistent_agent")


def test_update_pending_plan_adds_text(plan_dir):
    plan = _make_plan()
    save_pending_plan(agent_id="example_macro", plan=plan, directive=FakeDirective(), context_files={})

    loaded = load_pending_plan("example_macro")
    actions = loaded["actions"]
    for action in actions:
        if action["action"] == "comment":
            action["text"] = "this is my comment"
        if action["action"] == "post":
            action["text"] = "two paragraphs here\n\nsecond paragraph about $BTC"

    update_pending_plan("example_macro", actions)
    reloaded = load_pending_plan("example_macro")
    assert reloaded.get("text_authored_at") is not None
    comment = next(a for a in reloaded["actions"] if a["action"] == "comment")
    assert comment["text"] == "this is my comment"


def test_load_plan_for_execution_with_text(plan_dir):
    plan = _make_plan()
    save_pending_plan(agent_id="example_macro", plan=plan, directive=FakeDirective(), context_files={})

    loaded = load_pending_plan("example_macro")
    for action in loaded["actions"]:
        if action["action"] == "comment":
            action["text"] = "solid comment"
        if action["action"] == "post":
            action["text"] = "first paragraph\n\nsecond paragraph"
    update_pending_plan("example_macro", loaded["actions"])

    agent_plan = load_plan_for_execution("example_macro")
    assert len(agent_plan.actions) == 3


def test_load_plan_for_execution_without_text_raises(plan_dir):
    plan = _make_plan()
    save_pending_plan(agent_id="example_macro", plan=plan, directive=FakeDirective(), context_files={})

    with pytest.raises(ValueError, match="without text"):
        load_plan_for_execution("example_macro")


def test_delete_pending_plan(plan_dir):
    plan = _make_plan()
    save_pending_plan(agent_id="example_macro", plan=plan, directive=FakeDirective(), context_files={})
    delete_pending_plan("example_macro")

    with pytest.raises(FileNotFoundError):
        load_pending_plan("example_macro")
