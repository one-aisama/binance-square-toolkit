import pytest
from src.db.database import init_db
from src.session.credential_store import CredentialStore


@pytest.fixture
async def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    return CredentialStore(db_path)


async def test_save_and_load(store):
    cookies = {"session": "abc123", "p20t": "token"}
    headers = {"csrftoken": "xyz", "bnc-uuid": "uuid-1"}
    await store.save("account_1", cookies, headers)

    cred = await store.load("account_1")
    assert cred is not None
    assert cred["cookies"] == cookies
    assert cred["headers"] == headers
    assert cred["valid"] is True
    assert cred["harvested_at"] is not None
    assert cred["expires_at"] is not None


async def test_load_nonexistent(store):
    cred = await store.load("nonexistent")
    assert cred is None


async def test_invalidate(store):
    await store.save("acc", {"a": 1}, {"b": 2})
    await store.invalidate("acc")
    cred = await store.load("acc")
    assert cred["valid"] is False


async def test_is_valid(store):
    await store.save("acc", {"a": 1}, {"b": 2})
    assert await store.is_valid("acc") is True
    await store.invalidate("acc")
    assert await store.is_valid("acc") is False


async def test_is_valid_nonexistent(store):
    assert await store.is_valid("nope") is False


async def test_upsert_overwrites(store):
    await store.save("acc", {"old": 1}, {"old": 1})
    await store.save("acc", {"new": 2}, {"new": 2})
    cred = await store.load("acc")
    assert cred["cookies"] == {"new": 2}
    assert cred["headers"] == {"new": 2}
    assert cred["valid"] is True


async def test_upsert_revalidates(store):
    await store.save("acc", {"a": 1}, {"b": 2})
    await store.invalidate("acc")
    assert await store.is_valid("acc") is False
    # Re-save should re-validate
    await store.save("acc", {"c": 3}, {"d": 4})
    assert await store.is_valid("acc") is True
