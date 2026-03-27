---
globs: [".env*", "config/accounts/*"]
---

# Правила безопасности

- НИКОГДА не коммитить API ключи, токены или credentials в репозиторий.
- Все API ключи (ANTHROPIC_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY) должны быть только в `.env`.
- `.env` в `.gitignore` — проверять перед коммитом.
- YAML-файлы аккаунтов в `config/accounts/` содержат `adspower_profile_id` и конфиги прокси — обращаться как с чувствительными данными.
- Захваченные credentials (cookies, headers с csrftoken, fvideo-id, fvideo-token) хранятся в SQLite, никогда в коде или конфигах.
- Никогда не логировать полные значения cookies или auth-заголовков — обрезать в лог-сообщениях.
- Каждый аккаунт должен использовать свой прокси и AdsPower профиль — никогда не шарить credentials между аккаунтами.
