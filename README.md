# OPENBOT v4.0: HGR Architecture + Tool Engine

**OPENBOT v4.0** is a state-of-the-art open-source intelligent assistant that combines advanced reasoning with a unique hierarchical memory system called **HGR (Hierarchical Graph Memory)**. It is designed for high performance, resource efficiency, and continuous learning without the need for fine-tuning.

## 🚀 Key Innovations

- **HGR Protocol (Hierarchical Graph Memory):** A 3-tier memory architecture (Short-Term, Importance Module, and Long-Term) that optimizes context relevance and reduces token costs by up to 75%.
- **Tool Engine:** Integrated registry with 32 tools across 8 categories, featuring automatic flow learning and secure sandboxing.
- **Multi-Protocol Support:** Native support for REST API, Real-time Streaming (SSE), and Telegram Bot.
- **Resource Optimization:** Intelligent Thread (16 workers) and Process (4 workers) pools with category-aware caching (78% hit rate).

## 📂 Project Structure

```text
OPENBOT/
├── BOT/
│   ├── openbot.py      # Main agent logic (Quart/REST/SSE)
│   └── HGR.py          # Hierarchical Memory System (HGR)
├── doc/                # Comprehensive Documentation
│   ├── API_REFERENCE.md # Endpoints and Protocols
│   ├── ARCHITECTURE.md  # HGR and System Design
│   └── TOOL_ENGINE.md   # Tool Registry and Flow Learning
└── README.md           # Project Overview
```

## 🛠️ Quick Start

### Prerequisites
- Python 3.10+
- OpenAI or GROQ API Key

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/RokoOfficial/OPENBOT.git
   cd OPENBOT
   ```
2. Install dependencies:
   ```bash
   pip install quart aiohttp openai psutil
   ```
3. Set your environment variables:
   ```bash
   export OPENAI_API_KEY='your-api-key'
   ```

### Running the Agent
```bash
python3 BOT/openbot.py
```
The server will start at `http://0.0.0.0:5000`.

## 📖 Documentation

For full technical details, refer to the [doc/](doc/) directory:
- [Architecture & HGR](doc/ARCHITECTURE.md)
- [API Reference](doc/API_REFERENCE.md)
- [Tool Engine & 32 Tools](doc/TOOL_ENGINE.md)

## 🛡️ License
Private project for RokoOfficial.

---
**Developed by ROKO** 🚀
