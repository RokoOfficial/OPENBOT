# HGR v4.0 — Hierarchical Grounded Reasoning
## Persistent Memory System for Cognitive Agents · OPENBOT

> **Version:** 4.0 · **License:** Open-Source · **Runtime:** Python 3.10+ · **Database:** SQLite (WAL)

---

## Table of Contents

1. [Overview](#overview)
2. [Core Architecture](#core-architecture)
3. [Database Schema](#database-schema)
4. [Components](#components)
5. [Public API Reference](#public-api-reference)
6. [Configuration Parameters](#configuration-parameters)
7. [Data Flow](#data-flow)
8. [Integration with OPENBOT](#integration-with-openbot)
9. [REST Endpoints](#rest-endpoints)
10. [Automatic Fact Extraction](#automatic-fact-extraction)
11. [Cron Scheduling](#cron-scheduling)
12. [Quick Start](#quick-start)
13. [Improvements over v3.1](#improvements-over-v31)

---

## Overview

**HGR** (Hierarchical Grounded Reasoning) is the persistent cognitive memory subsystem of OPENBOT v4.0. It equips the agent with three complementary memory layers — a short-term RAM cache, a session-scoped in-memory store, and a long-term SQLite persistence layer — all orchestrated through a single unified database file (`agent_memory.db`).

Key guarantees provided by HGR:

- The LLM **never loses conversational context** across server restarts; the chat cache is fully reconstructed from SQLite on startup.
- User facts are **automatically extracted** from every exchange using multilingual regex patterns and are **always injected** into the system prompt on the following request.
- A **dynamic relevance threshold** ensures the agent never starts a request without contextual grounding, even when lexical similarity to prior steps is low.
- A native **asyncio cron scheduler** is integrated directly into the memory manager, requiring no external dependencies.

---

## Core Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  MemoryEnhancedAgent                     │
│          (public interface used by agent_loop)           │
└─────────────────────────┬────────────────────────────────┘
                          │
             ┌────────────▼────────────┐
             │  HierarchicalMemory     │
             │       Manager           │
             └─┬──────┬──────┬─────┬──┘
               │      │      │     │
      ┌────────▼─┐ ┌───▼──┐ ┌▼──┐ ┌▼────────┐
      │  Chat    │ │Facts │ │Ctx│ │  Cron   │
      │ History  │ │ Mgr  │ │Stp│ │ Manager │
      │ Manager  │ │      │ │Mgr│ │         │
      └────────┬─┘ └───┬──┘ └┬──┘ └┬────────┘
               │       │     │     │
            ┌──▼───────▼─────▼─────▼──┐
            │        HGRDatabase       │
            │     (agent_memory.db)    │
            │   WAL · row_factory=Row  │
            └──────────────────────────┘
```

**Memory layers:**

| Layer | Storage | TTL | Scope |
|---|---|---|---|
| Short-term | RAM deque | 1 hour | Recent reasoning steps |
| Medium-term | RAM deque | 24 hours | Session context |
| Long-term | SQLite | Permanent | Facts, chat history, cron jobs |

---

## Database Schema

All state is stored in a **single SQLite file** (`agent_memory.db`) with four tables.

### `chat_log` — Persistent conversation history

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `user_id` | TEXT | User identifier |
| `role` | TEXT | `user` or `assistant` |
| `content` | TEXT | Message body |
| `timestamp` | REAL | Unix epoch |
| `session_id` | TEXT | Daily MD5 hash |

Index: `idx_chat_user_ts ON chat_log(user_id, timestamp DESC)`

---

### `facts` — Key-value user/project knowledge store

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `user_id` | TEXT | User identifier |
| `key` | TEXT | Fact name (UNIQUE per user) |
| `value` | TEXT | Fact value |
| `importance` | REAL | 0.0–1.0 relevance weight |
| `category` | TEXT | e.g. `general`, `auto_extracted` |
| `tags` | TEXT | JSON array |
| `access_count` | INTEGER | Read frequency counter |
| `last_accessed` | REAL | Unix epoch |
| `created_at` | REAL | Unix epoch |

---

### `context_steps` — Agent technical reasoning steps

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `user_id` | TEXT | User identifier |
| `session_id` | TEXT | Session hash |
| `query` | TEXT | Original user query |
| `thought` | TEXT | Agent's internal reasoning |
| `action` | TEXT | Action taken (e.g. `continue`, `tool_call`) |
| `confidence` | REAL | 0.0–1.0 |
| `importance` | REAL | 0.0–1.0 |
| `tool_used` | TEXT | Tool name if a tool was called |
| `tool_result` | TEXT | Truncated tool output (max 300 chars) |
| `keywords` | TEXT | Space-separated keyword tokens |
| `timestamp` | REAL | Unix epoch |

---

### `cron_jobs` — Scheduled tasks

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `user_id` | TEXT | Job owner |
| `name` | TEXT | Human-readable job name |
| `description` | TEXT | Description |
| `schedule` | TEXT | 5-field cron or `every:Ns/Nm/Nh` |
| `task_type` | TEXT | `shell`, `agent`, etc. |
| `task` | TEXT | Command or natural-language instruction |
| `status` | TEXT | `active`, `paused`, `done` |
| `last_run` | REAL | Unix epoch |
| `next_run` | REAL | Unix epoch |
| `run_count` | INTEGER | Total successful executions |
| `last_output` | TEXT | Last execution result string |
| `created_at` | REAL | Unix epoch |

---

## Components

### `MemoryConfig`

Central configuration dataclass. All parameters have production-ready defaults and can be patched at runtime via `PATCH /api/memory/config`.

```python
@dataclass
class MemoryConfig:
    db_path:              str   = "agent_memory.db"
    short_term_size:      int   = 30       # RAM deque capacity
    short_term_ttl:       int   = 3600     # 1 hour
    medium_term_size:     int   = 100      # RAM deque capacity
    medium_term_ttl:      int   = 86400    # 24 hours
    min_relevance_score:  float = 0.05     # dynamic threshold floor
    importance_threshold: float = 0.3      # min to persist steps to DB
    max_chat_history:     int   = 200      # max messages per user in DB
    chat_history_to_llm:  int   = 40       # messages sent per LLM request
    max_facts_in_prompt:  int   = 20       # facts injected per system prompt
    cron_tick_interval:   int   = 30       # scheduler check interval (seconds)
```

---

### `RelevanceScorer`

Stateless utility class. Scores memory relevance using keyword overlap (Jaccard similarity), recency decay, and access-frequency boost.

| Method | Returns | Description |
|---|---|---|
| `keywords(text)` | `set[str]` | Tokenizes text, removes stop words (EN + PT) |
| `score(query, text, timestamp, access_count)` | `float` | 0.0–1.0 relevance score |
| `importance(thought, confidence, has_result)` | `float` | Calculates step importance |

---

### `HGRDatabase`

Low-level SQLite wrapper. All tables are created on first instantiation.

```python
db = HGRDatabase("agent_memory.db")
db.execute(sql, params)       # INSERT / UPDATE / DELETE
db.fetchone(sql, params)      # → sqlite3.Row | None
db.fetchall(sql, params)      # → List[sqlite3.Row]
```

Pragmas applied: `PRAGMA journal_mode=WAL` · `PRAGMA foreign_keys=ON`

---

### `ChatHistoryManager`

Manages the full persistent conversation log.

- Every message is immediately written to `chat_log`.
- An in-memory `deque` cache is populated lazily from SQLite after a restart.
- DB rows per user are capped at `max_chat_history`; oldest messages are pruned automatically.

```python
chat.add(user_id, role, content)          # persist + update cache
chat.get(user_id, last_n=40)              # → List[{"role": str, "content": str}]
chat.clear(user_id)                       # → int (rows deleted)
```

---

### `FactsManager`

Manages persistent key-value facts about users, projects, and preferences.

**Automatic extraction patterns (multilingual regex):**

| Pattern | Category | Importance |
|---|---|---|
| `me chamo` / `my name is` | `nome` | 0.95 |
| Email address | `email` | 0.90 |
| Preferred language (Python, JS, etc.) | `linguagem_preferida` | 0.80 |
| Active project | `projeto_ativo` | 0.75 |
| Location (`sou de` / `I live in`) | `localizacao` | 0.70 |
| Profession (`sou` / `I'm a`) | `profissao` | 0.65 |

**Core methods:**

```python
facts.store(user_id, key, value,
            importance=0.5, category="general", tags=None)  # → bool (True=created)
facts.get(user_id, key)                                      # → Fact | None
facts.get_all(user_id, min_importance=0.0)                   # → Dict[str, Fact]
facts.recall(user_id, category, limit, min_importance)       # → List[dict]
facts.delete(user_id, key, category, fact_id, delete_all)    # → int (deleted)
facts.search(user_id, term)                                  # → List[dict]
facts.format_for_prompt(user_id)                             # → str (for system prompt)
facts.extract_from_exchange(user_id, user_msg, bot_reply)    # → List[str] (keys)
facts.stats(user_id)                                         # → dict
```

---

### `ContextStepsManager`

Records and retrieves agent reasoning steps for cross-session context continuity.

- Steps with `importance >= importance_threshold` are persisted to DB.
- Lower-importance steps remain only in the short-term RAM deque.
- Retrieval uses a **dynamic threshold**: if no steps score above `min_relevance_score`, the threshold is progressively lowered until at least one result is found. Final fallback: the 3 most recent steps in the DB.

```python
steps.store(user_id, step: ContextStep)
steps.retrieve_relevant(user_id, query, max_items=5)  # → List[ContextStep]
steps.format_for_prompt(user_id, query)               # → str
```

---

### `CronManager`

Native `asyncio` task scheduler. No external dependencies required.

**Supported schedule formats:**

| Format | Example | Meaning |
|---|---|---|
| Interval (seconds) | `every:30s` | Every 30 seconds |
| Interval (minutes) | `every:5m` | Every 5 minutes |
| Interval (hours) | `every:2h` | Every 2 hours |
| Standard cron | `0 8 * * *` | Daily at 08:00 |

```python
crons.create(user_id, name, description, schedule, task_type, task)  # → CronJob
crons.list_jobs(user_id, status=None)                                 # → List[CronJob]
crons.pause(job_id, user_id)
crons.resume(job_id, user_id)
crons.delete(job_id, user_id)
await crons.run_now(job_id, user_id)                                  # → dict
crons.set_executor(fn: Callable)                                      # inject executor
await crons.start()                                                   # start scheduler loop
crons.format_next_run(job)                                            # → "in 5min" | "in 2h"
```

---

### `HierarchicalMemoryManager`

Central orchestrator. Holds references to all sub-managers and produces the final context block for the system prompt.

```python
mgr     = HierarchicalMemoryManager(config)
context = mgr.build_system_context(user_id, query)  # → str (always non-empty if data exists)
session = mgr.session_id(user_id)                   # → MD5 hash, resets daily
```

---

### `MemoryEnhancedAgent`

The **public interface** between `agent_loop` in `openbot.py` and the entire HGR subsystem. Maintains full backward compatibility with v3.1.

```python
agent = MemoryEnhancedAgent(config=None)

# Convenience property accessors
agent.db      # → HGRDatabase
agent.facts   # → FactsManager
agent.crons   # → CronManager

# Chat
agent.add_chat_message(user_id, role, content)
agent.get_chat_history(user_id, last_n=40)   # → List[dict]
agent.clear_chat_history(user_id)            # → int

# System prompt
agent.get_enhanced_system_prompt(user_id, query, base_prompt)  # → str

# Facts
agent.store_fact(user_id, key, value, importance, category, tags)
agent.get_user_facts(user_id)                        # → Dict[str, Fact]
agent.extract_and_store_facts(user_id, msg, reply)   # → List[str]

# Reasoning steps
agent.record_step(user_id, query, step_data)

# Stats
agent.get_stats(user_id)   # → dict

# Cron
agent.set_cron_executor(fn)
await agent.start_cron_scheduler()
```

---

## Public API Reference

### `get_enhanced_system_prompt(user_id, query, base_prompt) → str`

Enriches the base system prompt with two blocks:

1. **Facts block** — all known facts about the user, formatted as key-value pairs.
2. **Steps block** — the most relevant prior reasoning steps, with timestamps and confidence scores.

Both blocks are appended if data exists. The agent **never** starts a request without context.

---

### `extract_and_store_facts(user_id, user_msg, bot_reply) → List[str]`

Should be called after **every final LLM response**. Runs multilingual regex over both turns and persists any discovered facts. Returns a list of fact keys created or updated.

---

### `record_step(user_id, query, step_data) → None`

Records one agent reasoning step. The `step_data` dict accepts:

```python
{
    "thought":     str,    # internal monologue
    "action":      str,    # "continue", "tool_call", "final_answer"
    "confidence":  float,  # 0.0–1.0
    "tool":        str,    # tool name if invoked
    "result":      str,    # tool output
    "code_result": str,    # code execution output
}
```

---

## Configuration Parameters

| Parameter | Default | Description |
|---|---|---|
| `db_path` | `agent_memory.db` | SQLite file path |
| `short_term_size` | `30` | Short-term RAM deque capacity |
| `short_term_ttl` | `3600` | Short-term TTL (seconds) |
| `medium_term_size` | `100` | Medium-term RAM deque capacity |
| `medium_term_ttl` | `86400` | Medium-term TTL (seconds) |
| `min_relevance_score` | `0.05` | Dynamic threshold floor for context retrieval |
| `importance_threshold` | `0.3` | Minimum step importance to persist to DB |
| `max_chat_history` | `200` | Max messages stored per user |
| `chat_history_to_llm` | `40` | Messages forwarded per LLM request |
| `max_facts_in_prompt` | `20` | Max facts injected per system prompt |
| `cron_tick_interval` | `30` | Cron scheduler tick interval (seconds) |

---

## Data Flow

```
User message arrives
        │
        ▼
get_enhanced_system_prompt(user_id, query, base_prompt)
  ├── facts.format_for_prompt(user_id)         → inject known user facts
  └── steps.format_for_prompt(user_id, query)  → inject relevant prior steps
        │
        ▼
agent_loop() → LLM call
  (enriched system prompt + last N chat messages)
        │
        ▼
record_step(user_id, query, step_data)          → store reasoning step
        │
        ▼
Final response returned to user
        │
        ▼
add_chat_message(user_id, "user", user_msg)
add_chat_message(user_id, "assistant", response) → persist both turns
        │
        ▼
extract_and_store_facts(user_id, user_msg, response) → mine new facts
```

---

## Integration with OPENBOT

HGR is imported at startup and a global instance is created:

```python
from HGR import MemoryEnhancedAgent, MemoryConfig

memory_agent = MemoryEnhancedAgent()
```

The instance is used throughout `openbot.py`:

```python
# Before every LLM call
system_prompt = memory_agent.get_enhanced_system_prompt(uid, query, BASE_PROMPT)

# After every final response
memory_agent.add_chat_message(uid, "user", user_msg)
memory_agent.add_chat_message(uid, "assistant", response)
memory_agent.extract_and_store_facts(uid, user_msg, response)
memory_agent.record_step(uid, query, step_data)
```

The cron executor is registered at startup:

```python
async def _hgr_cron_executor(job) -> str:
    # executes shell commands or agent tasks
    ...

memory_agent.set_cron_executor(_hgr_cron_executor)
await memory_agent.start_cron_scheduler()
```

---

## REST Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/memory/list` | List facts (`?category`, `?search`, `?limit`, `?min_importance`) |
| `GET` | `/api/memory/context-steps` | List reasoning steps (`?limit`) |
| `GET` | `/api/memory/stats` | Memory statistics |
| `PATCH` | `/api/memory/config` | Update MemoryConfig at runtime |
| `DELETE` | `/api/memory/clear` | Clear chat history |
| `GET` | `/api/crons/list` | List cron jobs (`?status`) |
| `POST` | `/api/crons/create` | Create a new cron job |
| `POST` | `/api/crons/run-now` | Execute a job immediately |
| `PATCH` | `/api/crons/pause` | Pause a job |
| `PATCH` | `/api/crons/resume` | Resume a job |
| `DELETE` | `/api/crons/delete` | Delete a job |

All endpoints require JWT Bearer token authentication via `require_auth()`.

---

## Automatic Fact Extraction

Facts are extracted proactively from every conversation exchange using compiled multilingual regex patterns.

**Example:**

```
User:  "My name is Ana and I work with TypeScript"
Bot:   "Hello Ana! TypeScript is a great choice."
```

Facts created:
- `nome` → `"Ana"` (importance: 0.95, category: `auto_extracted`)
- `linguagem_preferida` → `"TypeScript"` (importance: 0.80, category: `auto_extracted`)

These facts are available in the next request's system prompt immediately.

---

## Cron Scheduling

```python
# Standard 5-field cron (08:00 every day)
job = agent.crons.create(
    uid, "Daily Digest", "Morning summary",
    "0 8 * * *", "agent", "Summarize today's agenda"
)

# Interval shortcut (every 5 minutes)
job = agent.crons.create(
    uid, "Heartbeat", "System health check",
    "every:5m", "shell", "echo alive"
)

print(agent.crons.format_next_run(job))   # "in 4min"
```

---

## Quick Start

```python
from HGR import MemoryEnhancedAgent

agent = MemoryEnhancedAgent()
uid   = "user_001"

# 1. Store a fact manually
agent.store_fact(uid, "preferred_language", "Python", importance=0.8)

# 2. Record a conversation turn
agent.add_chat_message(uid, "user",      "Hello, I'm building a FastAPI service")
agent.add_chat_message(uid, "assistant", "Great! FastAPI is excellent for REST APIs.")

# 3. Auto-extract facts from the exchange
keys = agent.extract_and_store_facts(
    uid,
    "Hello, I'm building a FastAPI service",
    "Great! FastAPI is excellent for REST APIs."
)
print(keys)   # ["projeto_ativo"]

# 4. Enrich the next system prompt
prompt = agent.get_enhanced_system_prompt(uid, "help with routing", "You are OPENBOT.")
print(prompt)   # base prompt + facts block + steps block

# 5. Check statistics
print(agent.get_stats(uid))
```

---

## Improvements over v3.1

| Feature | v3.1 | v4.0 |
|---|---|---|
| Chat history persistence | RAM only — lost on restart | SQLite — survives restarts |
| Facts storage | Separate `MemorySQL` class | Unified `facts` table in `agent_memory.db` |
| Context injection | Optional | Always mandatory |
| Fact extraction | Manual only | Automatic after every exchange |
| Relevance threshold | Static | Dynamic — never returns empty context |
| Cron scheduler | External library | Native `asyncio` in HGR |
| Database files | Multiple separate DBs | Single `agent_memory.db` |
| Recency boost | No | Yes — recent memories ranked higher |
| Frequency boost | No | Yes — frequently accessed facts ranked higher |

---

```
agent_memory.db
├── chat_log         ← full conversation history (persistent across restarts)
│     └── RAM cache rebuilt on startup
├── facts            ← user/project key-value store
│     ├── auto-extracted after every exchange
│     └── injected into every system prompt
├── context_steps    ← agent reasoning steps
│     ├── persisted if importance ≥ 0.3
│     └── retrieved by dynamic relevance scoring
└── cron_jobs        ← scheduled tasks
      ├── asyncio scheduler, tick every 30s
      └── executor callback registered from openbot.py
```

---

*Source: `HGR.py` — OPENBOT v4.0 · March 2026 · Language: English*
