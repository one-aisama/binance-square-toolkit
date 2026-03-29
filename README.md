# Binance Square Toolkit

An AI-agent-driven SDK for managing Binance Square activity. You give the project to Claude Code (or Codex), and it creates autonomous sub-agents that operate your Binance Square accounts — posting, commenting, liking, building relationships, growing your audience.

**This is not the final version**, but everything is functional and working.

## How It Works

You don't write scripts or configure pipelines manually. You open this project in Claude Code or Codex, describe what you want, and the AI session handles the rest.

```
You → Claude Code / Codex → reads the project → creates sub-agents
                                                      ↓
                              Each agent manages one Binance Square account
                              Posts, comments, likes, follows, builds relationships
                              Learns from results, adapts strategy over time
```

Through a Claude Code or Codex session you can:
- Set up agents with unique personalities and writing styles
- Configure daily limits (how many posts, likes, comments per day)
- Fix bugs or customize anything to your needs
- Add new agents for additional Binance accounts

## Requirements

| What | Why |
|------|-----|
| **Python 3.12+** | Runtime |
| **AdsPower** | Anti-detect browser — each agent needs its own browser profile with a logged-in Binance account |
| **Claude Code or Codex** | The AI that reads this project and operates your agents |
| **Binance account(s)** | One per agent, logged in through AdsPower profiles |

### Optional
| What | Why |
|------|-----|
| **Anthropic / OpenAI / DeepSeek API key** | For the built-in comment generator (CommentGenerator). Not required if your AI session generates content directly |
| **Mobile proxies** | Recommended for multiple accounts — one proxy per AdsPower profile |

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/one-aisama/binance-square-toolkit.git
cd binance-square-toolkit
pip install -r requirements.txt
playwright install chromium
```

### 2. Create `.env`

```
DB_PATH=data/bsq.db

# Optional — only if using built-in CommentGenerator
ANTHROPIC_API_KEY=your-key
OPENAI_API_KEY=your-key
DEEPSEEK_API_KEY=your-key
```

### 3. Set up AdsPower

- Install [AdsPower](https://www.adspower.com/)
- Create a browser profile
- Log into your Binance account through that profile
- Note the profile ID from AdsPower

### 4. Open in Claude Code

```bash
claude  # or open in Codex
```

Tell it: *"Read the project. Set up an agent for my AdsPower profile [your-profile-id]. Give it a personality and start a session."*

That's it. Claude reads CLAUDE.md, understands the architecture, creates the agent config, and runs it.

## What the Agents Do

Each agent operates autonomously:
- **Reads the market** — prices, trends, technical analysis, news
- **Browses the feed** — finds posts worth engaging with (filters spam automatically)
- **Comments** — data-backed, personality-driven, on posts by influencers with real audiences
- **Posts** — with charts, images, $CASHTAGS, market sentiment
- **Builds relationships** — tracks which creators respond, focuses effort where it works
- **Learns** — metrics are collected after each action, performance data shapes future strategy

## Architecture

```
┌─────────────────────────────────────────┐
│         STRATEGY (LLM — brain)          │
│   analyst → planner → reviewer          │
└──────────────────┬──────────────────────┘
                   │ session plan
┌──────────────────▼──────────────────────┐
│         RUNTIME (code — guardrails)     │
│   limits, circuit breaker, cooldowns    │
│   agent cannot bypass this layer        │
└──────────────────┬──────────────────────┘
                   │ controlled actions
┌──────────────────▼──────────────────────┐
│              SDK (hands)                │
│   post, comment, like, follow, parse    │
└──────────────────┬──────────────────────┘
                   │ results
┌──────────────────▼──────────────────────┐
│      METRICS + MEMORY (eyes + memory)   │
│   collect outcomes → score → learn      │
└─────────────────────────────────────────┘
```

- **Runtime** enforces limits in code — the agent literally cannot exceed daily action limits or ignore cooldowns
- **Metrics** are collected hours after each action (views, likes, replies) and aggregated automatically
- **Memory** compacts session logs into actionable insights — what content type works, which creators respond, best times to post

## Project Structure

```
binance-square-toolkit/
  src/
    sdk.py              # Unified facade — all agent actions go through here
    session/            # AdsPower + Playwright CDP browser automation
    bapi/               # HTTP client for Binance API (parsing, likes)
    runtime/            # ActionGuard (limits), HumanBehavior (delays)
    metrics/            # Collector, Scorer, Store — delayed outcome tracking
    memory/             # Compactor — generates performance.md from data
    strategy/           # Planner, Analyst, Reviewer, FeedFilter
    content/            # Validators, market data, TA, news
    activity/           # Engagement orchestration
    accounts/           # Config loading, daily limits
    db/                 # SQLite schema
  agents/
    aisama/             # Example agent with full memory structure
  config/
    personas.yaml       # Agent personality definitions
    content_rules.yaml  # Writing style rules, banned phrases
    settings.yaml       # Global settings
  tests/                # 19 test files
  session_run.py        # Example session entry point
```

## Recommended: AI Dev Framework

If you want to modify this project structurally — add modules, redesign architecture, build new features — use [AI Dev Framework](https://github.com/one-aisama/ai-dev-framework). It provides a structured workflow for AI-assisted development: from idea to architecture to specs to implementation, with quality gates at each stage. This ensures changes are coherent, well-documented, and don't break what already works.

## License

MIT
