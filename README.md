# OPENBOT: Reasoning Agent with Hierarchical Memory (HGR)

**OPENBOT** is an advanced reasoning agent designed for complex problem-solving, featuring a sophisticated hierarchical memory system called **HGR (Hierarchical General Recall)**. It integrates Large Language Models (LLMs) with a persistent memory architecture to ensure continuity, learning, and high-precision execution.

## 🚀 Key Features

- **Hierarchical Memory (HGR):** A 3-tier memory system (Short, Medium, and Long-term) that allows the agent to remember past interactions, learn from errors, and maintain context across sessions.
- **Autonomous Reasoning:** Uses a "Thought-Action-Observation" loop to decompose complex queries into manageable steps.
- **Code Execution Sandbox:** Capable of writing and executing Python code in a secure environment to perform calculations, data analysis, or system tasks.
- **Flask-based API:** Ready-to-use REST API with support for both standard JSON responses and real-time Server-Sent Events (SSE) streaming.
- **Resource Monitoring:** Real-time tracking of CPU and memory usage during execution.

## 📂 Project Structure

```text
OPENBOT/
├── BOT/
│   └── openbot.py      # Main agent logic and API server
├── HGR.py              # Hierarchical Memory System (HGR)
├── doc/                # Technical documentation
│   ├── API_GUIDE.md    # API usage and endpoints
│   └── ARCHITECTURE.md # System design and HGR details
├── agent_memory.db     # SQLite database (generated at runtime)
└── README.md           # Project presentation
```

## 🛠️ Quick Start

### Prerequisites
- Python 3.8+
- OpenAI API Key

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/RokoOfficial/OPENBOT.git
   cd OPENBOT
   ```
2. Install dependencies:
   ```bash
   pip install flask openai psutil
   ```
3. Set your API key:
   ```bash
   export OPENAI_API_KEY=\'your-api-key-here\'
   ```

### Running the Agent
```bash
python3 BOT/openbot.py
```
The server will start at `http://0.0.0.0:5000`.

## 📖 Documentation

For detailed information on how to use the API and understand the internal architecture, please refer to the [doc/](doc/) directory:
- [API Usage Guide](doc/API_GUIDE.md)
- [System Architecture](doc/ARCHITECTURE.md)

## 🛡️ License
This project is private and intended for internal use by RokoOfficial.

---
**Developed by ROKO**
