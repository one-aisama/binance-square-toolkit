"""Account and persona configuration loader."""

import os
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator

logger = logging.getLogger("bsq.accounts")


class ProxyConfig(BaseModel):
    host: str
    port: int


class LimitsConfig(BaseModel):
    posts_per_day: list[int] = [3, 5]
    likes_per_day: list[int] = [30, 60]
    comments_per_day: list[int] = [12, 24]
    reposts_per_day: list[int] = [0, 1]
    min_interval_sec: int = 90


class PersonaConfig(BaseModel):
    id: str
    name: str
    topics: list[str]
    style: str
    language: str = "en"


class AccountConfig(BaseModel):
    account_id: str
    persona_id: str
    binance_uid: str = ""
    adspower_profile_id: str
    proxy: ProxyConfig | None = None
    limits: LimitsConfig = LimitsConfig()
    persona: PersonaConfig | None = None  # Filled after merge


def load_personas(personas_path: str) -> dict[str, PersonaConfig]:
    """Load personas from YAML file. Returns dict keyed by persona id."""
    path = Path(personas_path)
    if not path.exists():
        raise FileNotFoundError(f"Personas file not found: {personas_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    personas = {}
    for p in data.get("personas", []):
        persona = PersonaConfig(**p)
        personas[persona.id] = persona
    logger.info(f"Loaded {len(personas)} personas from {personas_path}")
    return personas


def load_accounts(accounts_dir: str, personas_path: str) -> list[AccountConfig]:
    """Load all account configs from directory and merge with personas."""
    personas = load_personas(personas_path)

    accounts_path = Path(accounts_dir)
    if not accounts_path.exists():
        logger.warning(f"Accounts directory not found: {accounts_dir}")
        return []

    accounts = []
    for yaml_file in sorted(accounts_path.glob("*.yaml")):
        if yaml_file.name.startswith("_") or yaml_file.name.startswith("."):
            continue  # Skip example and hidden files

        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            continue

        account = AccountConfig(**data)

        # Merge persona
        persona = personas.get(account.persona_id)
        if persona is None:
            logger.warning(
                f"Account {account.account_id} references unknown persona {account.persona_id}"
            )
        account.persona = persona
        accounts.append(account)

    logger.info(f"Loaded {len(accounts)} accounts from {accounts_dir}")
    return accounts
