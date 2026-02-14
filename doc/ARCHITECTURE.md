# OPENBOT Architecture: HGR Protocol v4.0

The OPENBOT v4.0 architecture is centered around the **HGR (Hierarchical Graph Memory)** protocol, a 3-tier system designed to transform biological-like memory into digital persistence.

## 🧠 HGR Memory Hierarchy

| Tier | Location | Capacity | Purpose |
| :--- | :--- | :--- | :--- |
| **Nível 1: STM** | RAM | 20 Slots (FIFO) | Immediate conversational context (< 1ms access). |
| **Nível 2: Importance** | Logic | Threshold 0.5 | Adaptive module that decides what to migrate to LTM. |
| **Nível 3: LTM** | SQLite | Unlimited | Persistent storage for high-importance facts and patterns. |

### Importance Scoring Criteria
The system evaluates every interaction based on:
1. **Tool Usage:** +0.3 base + 0.1 per tool.
2. **Success:** +0.2 for successful operations.
3. **Complexity:** +0.1 for long messages or multiple intentions.
4. **Keywords:** +0.2 for action-oriented verbs (create, delete, execute).

## ⚙️ Resource Coordination

OPENBOT uses a **ResourceCoordinator** to manage execution efficiency:
- **Thread Pool (16 workers):** Optimized for I/O bound tasks (API calls, file system).
- **Process Pool (4 workers):** Optimized for CPU-bound tasks (Python execution, Crypto).
- **Connection Pool (aiohttp):** Manages persistent HTTP connections.

## 📈 Performance Metrics
- **Token Savings:** ~75% reduction compared to flat-memory architectures.
- **Cache Hit Rate:** ~78% global average.
- **Response Time:** ~187ms average latency.

---
**ROKO** 🚀
