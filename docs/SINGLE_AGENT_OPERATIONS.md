# Single-Agent Operations

Last updated: 2026-03-29

## Purpose

This document defines the current operational truth of the repository.
Right now the project is not a generic multi-account farm in daily use.
It is a single active Binance Square agent system centered on one real profile.

## Current Deployment

- Active agent: `aisama`
- Binance Square username: `aisama`
- AdsPower profile serial: `1`
- AdsPower user id: `your-adspower-profile-id`
- Primary objective: grow `aisama` into a recognizable Binance Square creator through comments, posts, relationship building, and data-backed content

## Source of Truth

The live runtime binding is stored in:

- [config/active_agent.yaml](config/active_agent.yaml)

That file defines:

- which agent is active
- which Binance username it controls
- which AdsPower profile serial is used by the SDK
- which AdsPower `user_id` is used by legacy account-driven flows
- which account config and agent directory belong to the active agent

## Runtime Paths

There are two architectural paths in the repo.
Only one is the primary operational path today.

### Primary path

`BinanceSquareSDK` -> browser actions / market data / news / TA -> agent session script

Concrete files:

- [src/sdk.py](src/sdk.py)
- [src/session/browser_actions.py](src/session/browser_actions.py)
- [src/runtime/agent_config.py](src/runtime/agent_config.py)
- [session_run.py](session_run.py)
- [agents/aisama/prompt.md](agents/aisama/prompt.md)

This is the path to use for real agent work.

### Secondary / legacy path

Scheduler and account-driven orchestration remain in the repo but are not the current control plane for daily operation.

Key files:

- [src/main.py](src/main.py)
- [src/scheduler/scheduler.py](src/scheduler/scheduler.py)
- [config/accounts/aisama.yaml](config/accounts/aisama.yaml)

Keep these files consistent, but do not treat them as the primary runtime unless the project is intentionally moved back to scheduler-first execution.

## Agent Assignment

`aisama` is the only active agent.
No second profile is assigned.
No cross-account behavior exists in the current deployment.

Supporting files:

- [agents/aisama/identity.md](agents/aisama/identity.md)
- [agents/aisama/strategy.md](agents/aisama/strategy.md)
- [agents/aisama/lessons.md](agents/aisama/lessons.md)
- [agents/aisama/journal.md](agents/aisama/journal.md)
- [agents/aisama/prompt.md](agents/aisama/prompt.md)

The agent's job is not just to post.
It is to become an influencer through:

- recognizable voice
- consistent posting
- comments on visible threads
- follow-up on replies
- performance review and adaptation

## Configuration Layout

### Runtime config

[config/active_agent.yaml](config/active_agent.yaml)

Use this when the question is: "Which agent controls which live profile right now?"

### Persona config

[config/personas.yaml](config/personas.yaml)

The checked-in `aisama` persona is the repo-level persona profile for the live agent.
It should stay aligned with the narrative identity in `agents/aisama/identity.md`.

### Legacy-compatible account config

[config/accounts/aisama.yaml](config/accounts/aisama.yaml)

Use this when older account-driven modules need a YAML account record.
This file exists for compatibility and should match the runtime config.

## How to Run the Agent

### Read-only smoke run

Use this when validating environment health before live work.

Checks to perform:

- `sdk.connect()`
- `sdk.get_my_stats()`
- `sdk.get_feed_posts(count=5, tab="recommended")`
- `sdk.get_feed_posts(count=5, tab="following")`
- `sdk.get_user_profile("aisama")`

Expected result:

- profile connects
- Creator Center stats load
- feed parsing returns posts
- no forced re-login mid-session

### Live session run

The current session script is:

- [session_run.py](session_run.py)

It now loads the active agent from runtime config instead of hardcoding the profile binding.

Session shape:

1. Gather context: market, news, TA
2. Check replies to the agent's previous comments
3. Browse feed and engage with selected posts
4. Create one post with chart
5. Verify session minimum before exit

## Operational Rules

- Do not run two competing operators against the same AdsPower profile at the same time.
- Do not log in manually during an SDK session unless recovery is required.
- Treat `aisama` as the single source of outward-facing identity.
- Preserve English-only output for public content.
- Prefer comments and relationship building over blind volume posting.

## Documentation Map

Use the docs in this order:

1. This file for current deployment truth
2. [README.md](README.md) for repository overview
3. [docs/agent_api.md](docs/agent_api.md) for SDK methods
4. [docs/design-spec.md](docs/design-spec.md) for architecture background
5. `docs/specs/*` for module-level detail

Historical note:

- [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) still contains the original multi-account ambition.
- That brief is useful for roadmap context, not for current operational assumptions.

## Multi-session Continuity

Long-running takeover work is tracked under:

- `.autonomous/single-agent-ops/`

That directory is local operational state, not product documentation.
Use it to continue the work without re-explaining the control model.
