# OPENBOT API Guide

The OPENBOT API provides endpoints to interact with the reasoning agent and manage its hierarchical memory.

## 📡 Endpoints

### 1. Send Message (Standard)
Sends a query to the agent and waits for the full reasoning loop to complete.

- **URL:** `/api/mensagem`
- **Method:** `POST`
- **Content-Type:** `application/json`

**Request Body:**
```json
{
  "user_id": "user_123",
  "message": "How much is 1234 * 5678?"
}
```

**Response:**
Returns a list of steps taken by the agent.
```json
{
  "steps": [
    {
      "step": 1,
      "thought": "I need to calculate 1234 * 5678.",
      "action": "execute_code",
      "code_result": "7006652",
      "time_seconds": 1.2
    },
    {
      "step": "FINAL",
      "thought": "The result of 1234 * 5678 is 7,006,652.",
      "time_seconds": 0.8
    }
  ]
}
```

---

### 2. Send Message (Streaming)
Streams the agent's reasoning steps in real-time using Server-Sent Events (SSE).

- **URL:** `/api/mensagem/stream`
- **Method:** `POST`
- **Content-Type:** `application/json`

**Request Body:**
```json
{
  "user_id": "user_123",
  "message": "Analyze the latest logs."
}
```

**Response:** `text/event-stream`
Each event is a JSON string representing a single step.

---

### 3. Memory Administration
Retrieve statistics about a user's persistent memory.

- **URL:** `/api/admin/memoria/<user_id>`
- **Method:** `GET`

**Response:**
```json
{
  "status": "success",
  "user_id": "user_123",
  "database_file": "agent_memory.db",
  "stats": {
    "short_term_count": 5,
    "long_term_count": 42,
    "active_sessions": 1
  }
}
```

## ⚙️ Configuration

The API behavior can be adjusted in `BOT/openbot.py`:
- `MAX_CODE_EXECUTIONS`: Maximum number of code runs per query (Default: 8).
- `MAX_AGENT_STEPS`: Maximum reasoning steps (Default: 32).
- `MODEL`: The LLM model used (Default: `gpt-4o-mini`).

---
**ROKO**
