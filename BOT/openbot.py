# ============================================================
# OPENROKO - AGENTE COM MEMÓRIA PERSISTENTE (HGR)
# API Quart com suporte a:
# - Raciocínio estruturado
# - Execução segura de código
# - Memória de longo prazo (SQLite)
# - Streaming SSE real
# - Compatível com Termux/Android
# ============================================================

import os
import json
import time
import hashlib
import logging
import asyncio
import subprocess
import psutil
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

from quart import Quart, request, jsonify, Response

# ============================================================
# IMPORTAÇÃO DO SISTEMA DE MEMÓRIA (HGR)
# ============================================================

try:
    from HGR import MemoryEnhancedAgent, MemoryConfig
    print("✅ HGR carregado com sucesso.")
except ImportError as e:
    print(f"❌ Erro ao importar HGR: {e}")
    exit(1)

# ============================================================
# CONFIGURAÇÕES GLOBAIS
# ============================================================

app = Quart(__name__)

# API KEY da OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️ OPENAI_API_KEY não definida no ambiente.")

import openai
openai.api_key = OPENAI_API_KEY
MODEL = "gpt-4o-mini"

# Limites de segurança
MAX_CODE_EXECUTIONS = 8
MAX_AGENT_STEPS = 32

# Pools para evitar travar o loop principal
thread_pool = ThreadPoolExecutor(max_workers=8)
process_pool = ProcessPoolExecutor(max_workers=2)

# Logging
logging.basicConfig(
    filename="agent_execution.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ============================================================
# CONFIGURAÇÃO DA MEMÓRIA HGR
# ============================================================

mem_config = MemoryConfig(
    long_term_db="agent_memory.db",  # Banco SQLite
    short_term_size=10,              # Memória temporária em RAM
    importance_threshold=0.6         # Só salva no DB se relevância > 0.6
)

memory_agent = MemoryEnhancedAgent(mem_config)

# ============================================================
# MONITORAMENTO DE RECURSOS
# ============================================================

def get_resource_usage():
    try:
        process = psutil.Process()
        cpu = psutil.cpu_percent(interval=0.1)
        mem = process.memory_info().rss / (1024 * 1024)
        return round(cpu, 1), round(mem, 1)
    except Exception:
        return 0.0, 0.0

# ============================================================
# EXECUÇÃO SEGURA DE CÓDIGO PYTHON
# ============================================================

def safe_exec_python(code: str) -> str:
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=15
        )
        return result.stdout.strip() or result.stderr.strip() or "(sem saída)"
    except subprocess.TimeoutExpired:
        return "Timeout: execução interrompida."
    except Exception as e:
        return str(e)

code_cache = {}

def get_code_hash(code: str):
    return hashlib.sha256(code.encode()).hexdigest()

async def execute_code(code: str, counter: dict):
    if counter["count"] >= MAX_CODE_EXECUTIONS:
        return "Limite de execuções atingido."

    cache_key = get_code_hash(code)
    if cache_key in code_cache:
        return code_cache[cache_key]

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(process_pool, safe_exec_python, code)

    code_cache[cache_key] = result
    counter["count"] += 1

    cpu, mem = get_resource_usage()
    logging.info(f"Execução código | CPU {cpu}% | MEM {mem}MB")

    return result

# ============================================================
# CHAMADA À OPENAI
# ============================================================

def sync_openai(messages):
    return openai.ChatCompletion.create(
        model=MODEL,
        messages=messages,
        temperature=0.2
    )

async def async_openai(messages):
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        thread_pool,
        lambda: sync_openai(messages)
    )
    return response.choices[0].message.content.strip()

# ============================================================
# LOOP PRINCIPAL DO AGENTE
# ============================================================

async def agent_loop(user_id: str, user_query: str):
    system_prompt = """Você é um agente inteligente com memória de longo prazo.
Sempre responda apenas com JSON:
{
  "thought": "...",
  "action": "continue | execute_code | final_answer",
  "code": "...",
  "answer": "...",
  "confidence": 0.0-1.0
}
"""
    enhanced_prompt = memory_agent.get_enhanced_system_prompt(
        user_id, user_query, system_prompt
    )

    messages = [
        {"role": "system", "content": enhanced_prompt},
        {"role": "user", "content": user_query}
    ]

    exec_counter = {"count": 0}
    step = 1

    while step <= MAX_AGENT_STEPS:
        start = time.time()
        response_text = await async_openai(messages)
        elapsed = round(time.time() - start, 2)

        try:
            response = json.loads(response_text)
        except:
            response = {
                "thought": "Erro no formato da resposta.",
                "action": "final_answer",
                "answer": response_text,
                "confidence": 0.5
            }

        code_result = None
        if response.get("action") == "execute_code":
            code_result = await execute_code(response.get("code", ""), exec_counter)
            messages.append({"role": "assistant", "content": json.dumps(response)})
            messages.append({"role": "user", "content": f"Resultado:\n{code_result}"})
        else:
            messages.append({"role": "assistant", "content": json.dumps(response)})

        memory_agent.record_step(user_id, user_query, {
            "thought": response.get("thought", ""),
            "action": response.get("action", ""),
            "confidence": response.get("confidence", 0.5),
            "code_result": code_result
        })

        yield {
            "step": step,
            "thought": response.get("thought"),
            "action": response.get("action"),
            "confidence": response.get("confidence"),
            "time_seconds": elapsed,
            "code_result": code_result
        }

        if response.get("action") == "final_answer":
            yield {
                "step": "FINAL",
                "thought": response.get("answer"),
                "confidence": response.get("confidence"),
                "time_seconds": elapsed
            }
            break

        step += 1

# ============================================================
# ROTAS DA API
# ============================================================

@app.route("/")
async def index():
    return jsonify({
        "status": "online",
        "bot": "OPENROKO",
        "memory_db": mem_config.long_term_db
    })

@app.route("/api/mensagem", methods=["POST"])
async def handle_message():
    data = await request.get_json()
    message = data.get("message", "").strip()
    user_id = data.get("user_id", "default_user")

    if not message:
        return jsonify({"error": "Mensagem vazia"}), 400

    steps = []
    async for step in agent_loop(user_id, message):
        steps.append(step)

    return jsonify({"steps": steps})

@app.route("/api/mensagem/stream", methods=["POST"])
async def stream_message():
    data = await request.get_json()
    message = data.get("message", "").strip()
    user_id = data.get("user_id", "default_user")

    if not message:
        return jsonify({"error": "Mensagem vazia"}), 400

    async def event_stream():
        async for step in agent_loop(user_id, message):
            yield f"data: {json.dumps(step, ensure_ascii=False)}\n\n"

    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/api/admin/memoria/<user_id>", methods=["GET"])
async def get_memory_stats(user_id):
    stats = memory_agent.get_stats(user_id)
    return jsonify({
        "status": "success",
        "user_id": user_id,
        "database": mem_config.long_term_db,
        "stats": stats
    })

# ============================================================
# START DO SERVIDOR
# ============================================================

if __name__ == "__main__":
    print("🚀 OPENROKO rodando na porta 5000")
    import hypercorn.asyncio
    from hypercorn.config import Config

    config = Config()
    config.bind = ["0.0.0.0:5000"]
    asyncio.run(hypercorn.asyncio.serve(app, config))