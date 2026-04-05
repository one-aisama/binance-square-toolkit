# Binance Square Toolkit — Operations Guide

## What Is This
SDK for autonomous activity on Binance Square. Three layers:
- **Software (this repository)** — executes actions: posts, comments, likes, follows
- **Operator (Claude Code / Codex session)** — assigns subagents to roles, manages execution
- **Subagents** — perform specific roles (persona, auditor, supervisor)

## How It Works
A Claude Code or Codex session is the **operator**. It gets the SDK and assigns subagents:

| Role | What It Does | Who |
|------|-------------|-----|
| **persona agent** | Works on Binance Square: writes posts, comments, likes, follows. Generates text itself | example_macro (profile 1), example_altcoin (profile 2) |
| **auditor** | Validates plan and content before publishing | agents/auditor/ |
| **supervisor** | Monitoring, coaching, behavior review of all persona agents | agents/supervisor/ |

Persona agents are subagents that **write text themselves** (they are LLMs). The software only executes their decisions via SDK. Code never generates text — ever.

## How to Run

### Production — via operator
```bash
# 1. Make sure AdsPower is running
# 2. Start the operator:
python scripts/run_operator.py --max-slots 4

# 3. Status in a separate terminal:
python scripts/operator_status.py
```
The operator scans `config/active_agent*.yaml` on its own, plans cycles, spawns persona subagents for text, executes via SDK.

### Manual mode — prepare/execute
```bash
python session_run.py --prepare --config config/active_agent.yaml
# → Agent session reads pending_plan.json, writes text, saves
python session_run.py --execute --config config/active_agent.yaml
```

### Tests
```bash
python -m pytest tests/ -v --ignore=tests/test_harvester_integration.py
```

## Architecture in a Nutshell

```
Agent (Claude Code session)
  ↓ decisions
session_run.py --prepare / --execute
  ↓
SDK (src/sdk.py) — unified facade
  ├── browser_actions.py  → posts, articles, reposts (Playwright CDP)
  ├── browser_engage.py   → likes, comments, follows (Playwright CDP)
  ├── browser_data.py     → feed collection, profile, comments
  └── bapi/               → httpx requests to Binance API
```

Runtime framework (`src/runtime/`) manages the cycle:
```
prepare (context → plan → audit) → AGENT WRITES TEXT → execute (audit → SDK → commit)
```

## Product Subagents

### Persona Agents — work on Binance Square
Each persona agent is a subagent with a unique personality. It writes text itself, makes its own decisions. The operator (Claude Code/Codex) assigns it to a profile and runs it.

| Agent | Profile | Focus | Files |
|-------|---------|-------|-------|
| **example_macro** | 1 | BTC/ETH, macro, market structure | `agents/example_macro/`, `config/persona_policies/example_macro.yaml` |
| **example_altcoin** | 2 | Altcoins, listings, sector rotation | `agents/example_altcoin/`, `config/persona_policies/example_altcoin.yaml` |
| *(new)* | 3-6 | Added as debugging progresses | YAML + folder in agents/ |

Each persona agent consists of:
- `agents/{id}/prompt.md` — system prompt (how to work, which tools)
- `agents/{id}/identity.md, style.md, strategy.md` — character and behavior
- `config/persona_policies/{id}.yaml` — numerical parameters (scoring, stages, templates)
- `config/active_agent.{id}.yaml` — binding to AdsPower profile

### Auditor — plan and content validation
Does not post. Checks persona agent plans before publishing: overlap, style, duplicates.
Files: `agents/auditor/prompt.md`

### Supervisor — monitoring and coaching
Does not post. Observes all persona agents, gives recommendations, tracks metrics.
Files: `agents/supervisor/prompt.md`, `agents/supervisor/reports/`

### Development Subagents (not product)
Separate category — help develop the SDK itself. Unrelated to Binance Square.

| Subagent | Role | File |
|----------|------|------|
| database-architect | DB schema, migrations | `.claude/agents/database-architect.md` |
| backend-engineer | Server logic | `.claude/agents/backend-engineer.md` |
| frontend-developer | UI components | `.claude/agents/frontend-developer.md` |
| qa-reviewer | Code review (read-only) | `.claude/agents/qa-reviewer.md` |
| spec-reviewer | Specification checking | `.claude/agents/spec-reviewer.md` |
| skeptic | Challenge architectural decisions | `.claude/agents/skeptic.md` |

## Code Navigation

| Task | Where to Look |
|------|--------------|
| **Launch (production)** | `scripts/run_operator.py` |
| **Status of all agents** | `scripts/operator_status.py` |
| Operator loop and scheduling | `src/operator/loop.py`, `scheduler.py`, `models.py` |
| Operator leases and recovery | `src/operator/leases.py`, `recovery.py` |
| Persona/auditor bridges | `src/operator/persona_bridge.py`, `auditor_bridge.py` |
| Understand what the SDK can do | `src/sdk.py`, `docs/agent_api.md` |
| How the agent plans actions | `src/runtime/deterministic_planner.py` |
| How post topic is selected | `src/runtime/editorial_brain.py` |
| How the plan is validated | `src/runtime/plan_auditor.py` |
| How the plan is executed | `src/runtime/plan_executor.py` |
| Limits and safety | `src/runtime/guard.py` |
| Coordination between agents | `src/runtime/comment_coordination.py`, `news_cooldown.py`, `topic_reservation.py` |
| Behavior (human-likeness) | `src/runtime/behavior.py` |
| CSS selectors for Binance | `src/session/page_map.py` |
| Persona settings | `config/persona_policies/{id}.yaml` |
| Runtime binding | `config/active_agent.{id}.yaml` |

## Documentation Navigation

| Document | Contents |
|----------|----------|
| `CLAUDE.md` | Main reference: stack, modules, architecture, status |
| `docs/agent_api.md` | All SDK methods with examples |
| `docs/design-spec.md` | Overall architecture, layers, tables |
| `docs/specs/spec_operator.md` | Operator control plane: state machine, scheduling, bridges |
| `docs/specs/spec_runtime.md` | Runtime details: planner, auditor, executor |
| `docs/specs/spec_session.md` | Browser automation: AdsPower, harvester, actions |
| `docs/specs/spec_bapi.md` | httpx client for Binance API |
| `src/*/CLAUDE.md` | Module references (files, functions, dependencies) |

## Agent Coordination

When running multiple agents simultaneously, 4 mechanisms operate:

| Mechanism | What It Does | TTL |
|-----------|-------------|-----|
| Topic reservations | Locks a post topic during planning | 2 hours |
| Comment locks | Prevents two agents from commenting on the same post | 30 min |
| News cooldowns | Prevents all agents from jumping on the same news | 90 min |
| Territory drift | Rejects plan if all posts are outside the agent's niche | — |
| Timing stagger | Spaces out agent cycles in time (0-300s offset) | — |

## Operating Modes

In `config/active_agent.{id}.yaml`:
```yaml
mode: "standard"      # default — normal operation by stages
mode: "individual"    # override — temporary campaign (expires_at)
mode: "test"          # dry-run — everything except actual execution
```

## Principle: Software = Hands, Agent = Brain

The persona agent participates in three places of each micro-cycle:

1. **STRATEGIZE** — persona reads briefing_packet + context → outputs strategic_directive
   (which coins, which angle, what to skip)
2. **AUTHOR** — persona reads plan with brief → writes post and comment text
3. **REFLECT** — persona updates strategic_state.md, open_loops.md, intent.md

Code **never** generates text or makes strategic decisions. Code only:
- Collects context (prepare)
- Compiles briefing_packet from memory (memory_compiler)
- Translates persona instructions into a plan (editorial_brain + planner)
- Validates (auditor)
- Executes via SDK (executor)

If there is an LLM call anywhere in the code for content generation or strategic decisions — that is a bug.

## Recommendations

- SDK (`src/sdk.py`) — the only way to interact with Binance Square. All actions go through it
- Behavior configuration — via YAML (`persona_policies/`, `active_agent.`), not via Python
- Adding a new agent — create YAML files and a folder in `agents/`, zero code changes
- Before changing runtime modules — run tests (390 tests, ~20 seconds)
- SQLite (`data/bsq.db`) — coordination layer. Per-agent state in files: `data/runtime/{id}/`
- Selectors in `page_map.py` are fragile — Binance UI can break them at any time

## Current Status
- 390 tests green
- 29 runtime modules
- 14 SQLite tables (10 runtime + 4 operator)
- 2 active personas (example_macro, example_altcoin)
- Updated: 2026-04-04
