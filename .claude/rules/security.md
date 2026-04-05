---
globs: [".env*", "config/accounts/*"]
---

# Security Rules

- NEVER commit API keys, tokens, or credentials to the repository.
- All API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY) must only be in `.env`.
- `.env` is in `.gitignore` — verify before committing.
- Account YAML files in `config/accounts/` contain `adspower_profile_id` and proxy configs — treat as sensitive data.
- Captured credentials (cookies, headers with csrftoken, fvideo-id, fvideo-token) are stored in SQLite, never in code or configs.
- Never log full cookie values or auth headers — truncate in log messages.
- Each account must use its own proxy and AdsPower profile — never share credentials between accounts.
