# Binance Square Toolkit

An AI-agent-driven SDK for managing Binance Square activity. You give the project to Claude Code (or Codex), and it creates autonomous sub-agents that operate your Binance Square accounts — posting, commenting, liking, building relationships, growing your audience.

## How It Works

You don't write scripts or configure pipelines manually. You open this project in Claude Code or Codex, and the AI session becomes the operator — it creates persona-agents, manages their cycles, and handles everything autonomously.

```
You -> Claude Code / Codex session
         |
         v
      Operator (manages all agents)
         |
         +-- Persona Agent 1 (aisama) -- writes posts, comments, builds audience
         +-- Persona Agent 2 (sweetdi) -- different style, different niche
         +-- Persona Agent N ...
         +-- Auditor -- validates content before publishing
         +-- Supervisor -- monitors performance, coaches agents
```

Each persona-agent:
- **Thinks strategically** — reads market data, decides what topics to cover
- **Writes its own text** — posts, comments, replies (the AI generates all content)
- **Learns from results** — adapts strategy based on what gets engagement
- **Has unique personality** — defined by identity, style, and strategy files

## Requirements

| What | Why |
|------|-----|
| **Python 3.12+** | Runtime |
| **AdsPower** | Anti-detect browser — each agent needs its own browser profile with a logged-in Binance account |
| **Claude Code or Codex** | The AI session that operates your agents |
| **Binance account(s)** | One per agent, logged in through AdsPower profiles |

### Optional
| What | Why |
|------|-----|
| **Mobile proxies** | Recommended for multiple accounts — one proxy per AdsPower profile |

## Setup Guide

### Step 1: Clone and install

```bash
git clone https://github.com/your-repo/binance-square-toolkit.git
cd binance-square-toolkit
pip install -r requirements.txt
playwright install chromium
```

### Step 2: Create `.env`

```bash
cp .env.example .env
```

Edit `.env`:
```
DB_PATH=data/bsq.db
```

### Step 3: Set up AdsPower

1. Install [AdsPower](https://www.adspower.com/)
2. Create a browser profile for each Binance account
3. Log into Binance through each profile
4. Note the **profile serial number** and **user_id** from AdsPower settings
5. Make sure AdsPower is running on `http://local.adspower.net:50325`

### Step 4: Create agent configuration

Copy the example config:
```bash
cp config/active_agent.example.yaml config/active_agent.yaml
```

Edit `config/active_agent.yaml`:
```yaml
active_agent:
  agent_id: "my_agent"
  binance_username: "MyBinanceUsername"
  profile_serial: "1"                    # Your AdsPower profile number
  adspower_user_id: "your_adspower_id"   # From AdsPower profile settings
  persona_id: "my_agent"
  agent_dir: "agents/my_agent"
  account_config_path: "config/accounts/my_agent.yaml"
  session_minimum:
    like: 20
    comment: 20
    post: 3
  market_symbols: ["BTC", "ETH", "SOL"]
  cycle_interval_minutes: [10, 15]
```

### Step 5: Create agent persona

Create agent directory:
```bash
mkdir -p agents/my_agent
```

Create `agents/my_agent/identity.md`:
```markdown
# Identity
I am a crypto analyst focused on market structure and positioning.
I look for where the crowd is wrong and where the tape tells a different story.
```

Create `agents/my_agent/style.md`:
```markdown
# Style
- Direct, analytical, no fluff
- Use $CASHTAGS for every coin mention
- 2-3 paragraphs per post
- Never end paragraphs with a period
- Sound like a real person, not a template
```

Create `agents/my_agent/strategy.md`:
```markdown
# Strategy
- Focus on BTC/ETH market structure
- Comment on visible creator threads
- Build relationships through repeat engagement
```

Copy the prompt template:
```bash
cp agents/aisama/prompt.md agents/my_agent/prompt.md
```
Edit the prompt to match your agent's identity.

### Step 6: Create persona policy

```bash
cp config/persona_policies/aisama.yaml config/persona_policies/my_agent.yaml
```
Edit to match your agent's coin preferences, scoring rules, and stage targets.

### Step 7: Open in Claude Code

```bash
claude
```

Tell the session:

> "Read the project. You are the operator. Start managing the agents. Use `python scripts/run_operator.py --max-slots 2` to begin."

Or for manual control:

> "Read the project. Prepare a cycle for aisama using `python session_run.py --prepare --config config/active_agent.yaml`, then write the text and execute."

### Step 8: Monitor

In a separate terminal:
```bash
python scripts/operator_status.py
```

This shows real-time status of all agents: what they're doing, cycles completed, errors, next run times.

## Architecture

```
Operator (persistent control plane)
  |
  +-- Scheduler (priority queue, slot management)
  |     picks which agent runs next
  |
  +-- Working Cycle (25-40 min per agent)
  |     |
  |     +-- 1. Compile briefing packet (memory -> compact context)
  |     +-- 2. Strategize (persona decides what to focus on)
  |     +-- 3. Prepare (collect market data, news, feed)
  |     +-- 4. Author (persona writes post/comment text)
  |     +-- 5. Audit (validate content quality)
  |     +-- 6. Execute (SDK publishes through browser)
  |     +-- 7. Reflect (persona updates strategy and memory)
  |     |
  |     +-- Repeat micro-cycles until time runs out
  |
  +-- Cooldown (10-15 min pause, then next cycle)
  |
  +-- Coordination (prevents agents from overlapping)
        topic locks, comment locks, news cooldowns
```

## Scaling

| Profiles | Browser Slots | Config |
|----------|--------------|--------|
| 2 | 2 | `--max-slots 2` |
| 6 | 4-6 | `--max-slots 6` |
| 20 | 4-6 | `--max-slots 6` (agents queue up) |
| 100 | 10-12 | `--max-slots 12` on powerful hardware |

Adding a new agent:
1. Create `config/active_agent.{id}.yaml`
2. Create `config/persona_policies/{id}.yaml`
3. Create `agents/{id}/` with identity, style, strategy, prompt
4. Restart operator — it picks up new configs automatically

## Key Principle

**The AI writes all content.** The code never generates text — not through templates, not through API calls, not through any mechanism. Each persona-agent is an LLM that reads context, decides what to write, and produces the text itself. The code only executes actions (publish, like, follow) and manages scheduling.

## Project Structure

```
binance-square-toolkit/
  src/
    sdk.py              # Unified SDK facade
    operator/           # Control plane: scheduler, state machine, bridges
    session/            # AdsPower + Playwright browser automation
    runtime/            # Guard, planner, auditor, executor, policies
    bapi/               # HTTP client for Binance API
    content/            # Validators, market data, TA, news
    metrics/            # Outcome tracking and scoring
    memory/             # Performance compaction
    strategy/           # Feed filter, session planner
  agents/
    aisama/             # Example persona (macro/analytical)
    sweetdi/            # Example persona (altcoin specialist)
    operator/           # Operator prompt
    auditor/            # Content auditor
    supervisor/         # Performance monitor
  config/
    persona_policies/   # Behavioral YAML per agent
    active_agent.example.yaml  # Template for agent config
    settings.yaml       # Global settings
  scripts/
    run_operator.py     # Production entry point
    operator_status.py  # Terminal dashboard
  tests/                # 390 tests
  session_run.py        # Manual prepare/execute interface
  AGENTS.md             # Operational guide
  CLAUDE.md             # Technical reference
```

## Documentation

| Document | What's inside |
|----------|--------------|
| `AGENTS.md` | How to run agents, architecture overview, coordination |
| `CLAUDE.md` | Technical reference: modules, tables, entry points |
| `docs/agent_api.md` | SDK method reference with examples |
| `docs/specs/spec_operator.md` | Operator specification: state machine, scheduling |
| `docs/specs/spec_runtime.md` | Runtime: planner, auditor, executor |

## License

MIT
