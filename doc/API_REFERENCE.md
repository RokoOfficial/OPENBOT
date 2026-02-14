# OPENBOT API Reference v4.0

OPENBOT supports three primary communication protocols to cater to different integration needs.

## 📡 1. REST API
Ideal for synchronous integrations and standard web clients.

### Endpoints
- `POST /api/auth/login`: Authenticate and receive JWT.
- `POST /api/chat`: Send a message and receive a full response.
- `GET /api/tools/list`: List all 32 available tools.

**Example Request:**
```json
{
    "message": "create a folder named app2027"
}
```

---

## 🌊 2. Streaming SSE
Server-Sent Events for real-time UI updates and "thought-by-thought" streaming.

- **Endpoint:** `POST /api/chat/stream`
- **Content-Type:** `text/event-stream`

**Event Types:**
- `thought`: The agent's reasoning process.
- `tool`: Notification of tool execution.
- `final`: The final answer to the user.

---

## 🤖 3. Telegram Bot
Direct interaction for end-users via the Telegram interface.

- **Features:** Supports file uploads, voice commands (transcribed), and persistent session memory.

---

## 🛠️ Error Codes

| Code | Description | Action |
| :--- | :--- | :--- |
| `INVALID_REQUEST` | Malformed JSON or missing fields. | Fix request body. |
| `AGENT_UNAVAILABLE` | System overload or pool exhaustion. | Retry after delay. |
| `RATE_LIMIT_EXCEEDED` | Too many requests per minute. | Respect headers. |

---
**ROKO** 🚀
