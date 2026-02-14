# OPENBOT Tool Engine v4.0

The Tool Engine is the core execution environment of OPENBOT, managing 32 specialized tools across 8 categories.

## 🛠️ Tool Categories

1. **PYTHON:** `python_execute`, `python_eval`, etc.
2. **FILESYSTEM:** `file_write`, `file_read`, `file_list`, `file_delete`.
3. **NETWORK:** `curl_request`, `port_scan`, `http_download`.
4. **SYSTEM:** `system_time`, `resource_monitor`.
5. **DATA:** `json_parse`, `csv_analyze`.
6. **CRYPTO:** Secure hashing and encryption tools.
7. **SHELL:** Controlled shell command execution.
8. **UTILITY:** Calculator, unit conversion, etc.

## 🔄 Flow Learning (Macros)
One of OPENBOT's most innovative features is the ability to learn **Tool Flows** automatically.

### How it works:
1. **Detection:** The `FlowLearner` analyzes tool execution history.
2. **Pattern Matching:** If a sequence (e.g., `file_write` → `file_list`) repeats > 5 times, it is identified as a pattern.
3. **Automation:** The agent suggests or automatically executes the sequence when a similar command is received.

## 🛡️ Sandboxing & Safety
- **Timeouts:** Every tool has a specific timeout (5s to 60s).
- **Isolamento:** CPU-bound tools run in a dedicated `ProcessPoolExecutor`.
- **Dangerous Flag:** Tools marked as `dangerous: true` require higher confidence scores or explicit user confirmation in certain modes.

---
**ROKO** 🚀
