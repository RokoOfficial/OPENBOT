# OPENBOT Architecture: Hierarchical General Recall (HGR)

OPENBOT is built upon a symbolic-neural hybrid architecture that prioritizes persistent context and verifiable reasoning.

## 🧠 The HGR Memory System

The core of OPENBOT is the **HGR (Hierarchical General Recall)** system, implemented in `HGR.py`. It manages context through three distinct tiers:

| Tier | Storage | TTL / Scope | Purpose |
| :--- | :--- | :--- | :--- |
| **Short-Term** | RAM (Deque) | Last 10 interactions | Immediate conversational context. |
| **Medium-Term** | RAM (Sessions) | 1 hour / Session | Active task context and session-specific logic. |
| **Long-Term** | SQLite DB | Persistent | High-importance facts, successful solutions, and user preferences. |

### Memory Consolidation
HGR automatically consolidates memories. When a session expires or a reasoning step is marked with high importance (score > 0.7), it is indexed into the SQLite database with keyword-based metadata for future retrieval.

## 🔄 Reasoning Loop

The agent operates in a continuous loop:
1. **Context Injection:** HGR retrieves relevant long-term memories based on the user's query and injects them into the system prompt.
2. **Thought:** The LLM generates a step-by-step plan.
3. **Action:** The agent decides to either execute Python code, continue reasoning, or provide a final answer.
4. **Observation:** Results from code execution are fed back into the loop.
5. **Memorization:** Every step is recorded by HGR, ensuring the agent "learns" from the current interaction.

## 🛡️ Security & Execution

- **Sandbox:** Code execution is performed in a separate subprocess with a 15-second timeout.
- **Resource Tracking:** `psutil` monitors CPU and memory usage to prevent runaway processes.
- **Concurrency:** Uses `ThreadPoolExecutor` for API calls and `ProcessPoolExecutor` for code execution to ensure the API remains responsive.

---
**ROKO**
