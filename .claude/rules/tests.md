---
globs: ["tests/**"]
---

# Testing Rules

- Use pytest with pytest-asyncio for async tests.
- Mock external services (Binance bapi, AI API, AdsPower) — never make live calls in tests.
- Test names describe WHAT is being tested, not implementation details.
- One assert per test where practical.
- Use fixtures for shared setup (mock BapiClient, mock CredentialStore, test DB).
- Integration tests with live services (e.g. `test_harvester_integration.py`) — in separate files, excluded from the default run.
- Run tests: `python -m pytest tests/ -v --ignore=tests/test_harvester_integration.py`
- Current test count: ~67 (may be outdated — check with `pytest --co -q`).
