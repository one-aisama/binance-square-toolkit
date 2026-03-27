"""Tests for activity engine."""

import pytest
from src.activity.target_selector import TargetSelector
from src.activity.randomizer import HumanRandomizer


# ---- TargetSelector tests ----

def _make_posts(n: int, base_views: int = 5000) -> list[dict]:
    return [
        {"post_id": str(i), "author_id": f"author_{i}", "view_count": base_views + i * 100}
        for i in range(n)
    ]


def test_select_like_targets():
    own = {"own_1", "own_2"}
    selector = TargetSelector(own, min_views=1000)
    posts = _make_posts(10)
    targets = selector.select_like_targets(posts, 5)
    assert len(targets) == 5


def test_excludes_own_accounts():
    own = {"author_0", "author_1"}
    selector = TargetSelector(own, min_views=0)
    posts = _make_posts(5)
    targets = selector.select_like_targets(posts, 10)
    author_ids = {p["author_id"] for p in targets}
    assert "author_0" not in author_ids
    assert "author_1" not in author_ids


def test_min_views_filter():
    selector = TargetSelector(set(), min_views=5500)
    posts = _make_posts(10, base_views=5000)
    targets = selector.select_like_targets(posts, 100)
    for t in targets:
        assert t["view_count"] >= 5500


def test_comment_targets_prefer_high_engagement():
    selector = TargetSelector(set(), min_views=0)
    posts = _make_posts(20)
    targets = selector.select_comment_targets(posts, 3)
    assert len(targets) == 3


def test_repost_targets_top_only():
    selector = TargetSelector(set(), min_views=0)
    posts = _make_posts(10)
    targets = selector.select_repost_targets(posts, 2)
    assert len(targets) == 2
    # Should be from top by views
    views = [t["view_count"] for t in targets]
    assert views == sorted(views, reverse=True)


# ---- Randomizer tests ----

def test_should_skip_rate():
    """Test that skip rate is roughly correct over many samples."""
    r = HumanRandomizer(delay_range=(0, 0), skip_rate=0.5)
    skips = sum(1 for _ in range(1000) if r.should_skip())
    assert 400 < skips < 600  # ~50% with some variance


async def test_human_delay_returns_value():
    r = HumanRandomizer(delay_range=(0, 0), skip_rate=0)
    delay = await r.human_delay()
    assert delay == 0.0
