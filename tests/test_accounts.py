"""Tests for account manager and limiter."""

import pytest
from pathlib import Path

from src.db.database import init_db
from src.accounts.manager import load_accounts, load_personas, AccountConfig, PersonaConfig
from src.accounts.limiter import ActionLimiter
from src.accounts.anti_detect import are_own_accounts, should_skip_post_by_author


# ---- Config loading tests ----

@pytest.fixture
def config_dir(tmp_path):
    """Create test config files."""
    # Personas
    personas_file = tmp_path / "personas.yaml"
    personas_file.write_text("""
personas:
  - id: test_analyst
    name: "Test Analyst"
    topics: [defi, trading]
    style: "analytical"
    language: en
  - id: test_news
    name: "Test News"
    topics: [news]
    style: "fast, factual"
    language: en
""")

    # Account configs
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    (accounts_dir / "analyst.yaml").write_text("""
account_id: analyst_1
persona_id: test_analyst
adspower_profile_id: "abc123"
binance_uid: "111"
proxy:
  host: proxy.example.com
  port: 8080
limits:
  posts_per_day: [2, 4]
  likes_per_day: [10, 20]
""")

    (accounts_dir / "news.yaml").write_text("""
account_id: news_1
persona_id: test_news
adspower_profile_id: "def456"
""")

    # Example file (should be skipped)
    (accounts_dir / "_example.yaml").write_text("""
account_id: example
persona_id: test_analyst
adspower_profile_id: "xxx"
""")

    return tmp_path


def test_load_personas(config_dir):
    personas = load_personas(str(config_dir / "personas.yaml"))
    assert len(personas) == 2
    assert "test_analyst" in personas
    assert personas["test_analyst"].style == "analytical"


def test_load_accounts(config_dir):
    accounts = load_accounts(
        str(config_dir / "accounts"),
        str(config_dir / "personas.yaml"),
    )
    assert len(accounts) == 2  # _example.yaml is skipped
    analyst = next(a for a in accounts if a.account_id == "analyst_1")
    assert analyst.persona is not None
    assert analyst.persona.id == "test_analyst"
    assert analyst.proxy is not None
    assert analyst.proxy.port == 8080
    assert analyst.limits.posts_per_day == [2, 4]


def test_load_accounts_missing_persona(config_dir):
    # Add account with bad persona reference
    (config_dir / "accounts" / "bad.yaml").write_text("""
account_id: bad_acc
persona_id: nonexistent
adspower_profile_id: "xxx"
""")
    accounts = load_accounts(
        str(config_dir / "accounts"),
        str(config_dir / "personas.yaml"),
    )
    bad = next(a for a in accounts if a.account_id == "bad_acc")
    assert bad.persona is None


# ---- Limiter tests ----

@pytest.fixture
async def limiter(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    return ActionLimiter(db_path)


async def test_check_allowed_within_limit(limiter):
    # No actions recorded yet, should be allowed
    allowed = await limiter.check_allowed("acc1", "like", [5, 10])
    assert allowed is True


async def test_check_allowed_at_limit(limiter):
    # Record enough actions to hit limit
    for _ in range(15):
        await limiter.record_action("acc1", "like", status="success")

    # Limit range [5, 10] — we did 15, should be denied
    allowed = await limiter.check_allowed("acc1", "like", [5, 10])
    assert allowed is False


async def test_record_action(limiter):
    await limiter.record_action("acc1", "post", target_id="post_123", status="success")
    count = await limiter.get_today_count("acc1", "post")
    assert count == 1


async def test_failed_actions_dont_count(limiter):
    await limiter.record_action("acc1", "like", status="failed", error="timeout")
    count = await limiter.get_today_count("acc1", "like")
    assert count == 0  # Failed actions not counted in success total


async def test_failed_action_increments_both_counters(limiter):
    """Failed action should increment action type counter AND errors_count in daily_stats."""
    import aiosqlite
    await limiter.record_action("acc1", "like", status="failed", error="timeout")
    today = __import__("datetime").date.today().isoformat()
    async with aiosqlite.connect(limiter._db_path) as db:
        cursor = await db.execute(
            "SELECT likes_count, errors_count FROM daily_stats WHERE account_id = ? AND date = ?",
            ("acc1", today),
        )
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1  # likes_count incremented
    assert row[1] == 1  # errors_count also incremented


async def test_repost_action_uses_correct_column(limiter):
    """Repost uses reposts_count, not reposts_count (plural s issue)."""
    import aiosqlite
    await limiter.record_action("acc1", "repost", status="success")
    today = __import__("datetime").date.today().isoformat()
    async with aiosqlite.connect(limiter._db_path) as db:
        cursor = await db.execute(
            "SELECT reposts_count FROM daily_stats WHERE account_id = ? AND date = ?",
            ("acc1", today),
        )
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1


# ---- Anti-detect tests ----

def test_are_own_accounts():
    own = {"acc1", "acc2", "acc3"}
    assert are_own_accounts("acc1", "acc2", own) is True
    assert are_own_accounts("acc1", "external", own) is False


def test_should_skip_own_posts():
    own = {"acc1", "acc2"}
    assert should_skip_post_by_author("acc1", own) is True
    assert should_skip_post_by_author("external", own) is False
