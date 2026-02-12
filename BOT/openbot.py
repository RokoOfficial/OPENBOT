from flask import Flask, request, jsonify, render_template, Response, stream_with_context
import openai
import os
import json
import time
import hashlib
import psutil
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import subprocess

# ────────────────────────────────────────────────────────────────
# IMPORTAÇÃO DO SISTEMA DE MEMÓRIA (HGR)
# ────────────────────────────────────────────────────────────────
try:
    from HGR import MemoryEnhancedAgent, MemoryConfig
    print("✅ Módulo HGR importado com sucesso. Banco de dados de memória ativo.")
except ImportError as e:
    print(f"❌ Erro ao importar HGR: {e}")
    exit(1)

# ────────────────────────────────────────────────────────────────
# CONFIGURAÇÕES GLOBAIS
# ────────────────────────────────────────────────────────────────

app = Flask(__name__)

# Configuração da API Key
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    # Fallback para teste local se necessário, ou levantar erro
    print("⚠️ AVISO: OPENAI_API_KEY não encontrada nas variáveis de ambiente.")
    # raise ValueError("OPENAI_API_KEY não está definida no ambiente")

openai.api_key = OPENAI_API_KEY
MODEL = "gpt-4o-mini"

# Limites de segurança
MAX_CODE_EXECUTIONS = 8
MAX_AGENT_STEPS = 32

# Pools de execução
thread_pool = ThreadPoolExecutor(max_workers=12)
process_pool = ProcessPoolExecutor(max_workers=4)

# Configuração de Logs
logging.basicConfig(
    filename="agent_execution_2026.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ────────────────────────────────────────────────────────────────
# INICIALIZAÇÃO DA MEMÓRIA (BANCO DE DADOS)
# ────────────────────────────────────────────────────────────────

# Configura a memória para usar um arquivo SQLite local
mem_config = MemoryConfig(
    long_term_db="agent_memory.db",  # O arquivo do banco de dados
    short_term_size=10,              # Memória recente em RAM
    importance_threshold=0.6         # Só salva no DB fatos com relevância > 0.6
)

# Instância global do Agente de Memória
memory_agent = MemoryEnhancedAgent(mem_config)

# ────────────────────────────────────────────────────────────────
# EXECUÇÃO DE CÓDIGO (SANDBOX SIMPLIFICADO)
# ────────────────────────────────────────────────────────────────

def get_resource_usage():
    process = psutil.Process()
    cpu = psutil.cpu_percent(interval=0.1)
    mem_mb = process.memory_info().rss / (1024*1024)
    return round(cpu, 1), round(mem_mb, 1)

def safe_exec_python(code: str) -> str:
    """Executa código Python em um subprocesso separado."""
    try:
        # Adiciona print explícito se não houver, para capturar saída de expressões simples
        if "print" not in code and "=" not in code.splitlines()[-1]:
             lines = code.splitlines()
             if lines:
                lines[-1] = f"print({lines[-1]})"
                code = "\n".join(lines)

        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True,
            timeout=15,
            env=os.environ.copy()
        )
        if result.returncode == 0:
            return result.stdout.strip() or "(código executado sem saída visual)"
        return f"Erro de execução:\n{result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Execução interrompida: timeout após 15 segundos"
    except Exception as e:
        return f"Erro interno: {str(e)}"

code_execution_cache = {}

def get_code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()

async def execute_code(code: str, exec_counter: dict) -> str:
    if exec_counter["count"] >= MAX_CODE_EXECUTIONS:
        return "Limite máximo de execuções de código atingido."
    
    cache_key = get_code_hash(code)
    if cache_key in code_execution_cache:
        return code_execution_cache[cache_key]
    
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(process_pool, safe_exec_python, code)
    
    code_execution_cache[cache_key] = result
    exec_counter["count"] += 1
    
    cpu, mem = get_resource_usage()
    logging.info(f"Código executado | CPU: {cpu}% | MEM: {mem}MB | Hash: {cache_key[:8]}")
    return result

# ────────────────────────────────────────────────────────────────
# INTEGRAÇÃO OPENAI
# ────────────────────────────────────────────────────────────────

def sync_openai_call(messages: list, max_tokens: int = 1200):
    return openai.ChatCompletion.create(
        model=MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.18, # Temperatura baixa para raciocínio preciso
        top_p=0.92
    )

async def async_openai(messages: list, max_tokens: int = 1200) -> dict:
    loop = asyncio.get_running_loop()
    raw_response = await loop.run_in_executor(
        thread_pool, lambda: sync_openai_call(messages, max_tokens)
    )
    content = raw_response.choices[0].message.content.strip()
    
    # Remove marcação de markdown se o modelo adicionar (```json ... ```)
    if content.startswith("```json"):
        content = content.replace("```json", "").replace("```", "")
    elif content.startswith("```"):
        content = content.replace("```", "")

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logging.warning(f"JSON inválido recebido: {content[:100]}...")
        return {
            "thought": "Erro no formato da resposta. Vou tentar novamente.",
            "action": "continue",
            "confidence": 0.3
        }

# ────────────────────────────────────────────────────────────────
# LOOP DO AGENTE (COM MEMÓRIA HGR)
# ────────────────────────────────────────────────────────────────

async def agent_loop(user_id: str, user_query: str):
    """
    Loop principal do agente.
    1. Recupera memória do banco de dados (HGR).
    2. Raciocina e age.
    3. Salva novos passos no banco de dados (HGR).
    """
    
    # Prompt base do sistema
    system_prompt_template = """\
Você é um agente de resolução de problemas extremamente cuidadoso e estruturado com memória de longo prazo.

IMPORTANTE:
1. Sempre verifique o "Contexto relevante" fornecido para não repetir erros passados.
2. Se você já resolveu algo parecido para este usuário, use essa informação.

Sempre responda APENAS com JSON válido contendo:
{
  "thought": "explique seu raciocínio passo a passo aqui",
  "action": "continue" (para raciocinar mais) | "execute_code" (para rodar python) | "final_answer" (resposta final),
  "code": "código Python APENAS se action=execute_code",
  "answer": "resposta final para o usuário APENAS se action=final_answer",
  "confidence": 0.0 a 1.0
}
"""

    # 1. RECUPERAÇÃO DE MEMÓRIA
    # O HGR busca no banco SQLite fatos relevantes ao user_id e à query atual
    # e injeta isso no prompt do sistema.
    enhanced_system_prompt = memory_agent.get_enhanced_system_prompt(
        user_id, 
        user_query, 
        system_prompt_template
    )

    messages = [
        {"role": "system", "content": enhanced_system_prompt},
        {"role": "user", "content": user_query.strip()}
    ]

    exec_counter = {"count": 0}
    step = 1

    while step <= MAX_AGENT_STEPS:
        start_time = time.time()
        
        # Chama LLM
        response = await async_openai(messages, max_tokens=1400)
        elapsed = round(time.time() - start_time, 2)

        # Executa código se necessário
        code_result = None
        if response.get("action") == "execute_code" and "code" in response:
            code_result = await execute_code(response["code"], exec_counter)
            response["observation"] = code_result # Adiciona ao histórico do chat local
            
            # Adiciona mensagem de observação para o LLM na próxima volta
            messages.append({"role": "assistant", "content": json.dumps(response)})
            messages.append({"role": "user", "content": f"Resultado do código:\n{code_result}"})
        else:
            messages.append({"role": "assistant", "content": json.dumps(response)})

        # 2. GRAVAÇÃO NA MEMÓRIA (BANCO DE DADOS)
        # Registra o passo atual no HGR. Se for importante, o HGR salvará no SQLite.
        memory_agent.record_step(user_id, user_query, {
            'thought': response.get("thought", ""),
            'action': response.get("action", "continue"),
            'confidence': response.get("confidence", 0.5),
            'code_result': code_result
        })

        # Envia update para o frontend
        yield {
            "step": step,
            "thought": response.get("thought", "—"),
            "confidence": response.get("confidence", 0.0),
            "action": response.get("action", "continue"),
            "time_seconds": elapsed,
            "code_result": code_result
        }

        # Verifica fim da execução
        if response.get("action") == "final_answer":
            final_answer = response.get("answer", "Concluído.")
            
            # Registro final extra para garantir que a resposta seja memorizada com alta importância
            memory_agent.record_step(user_id, user_query, {
                'thought': f"Conclusão Final: {final_answer}",
                'action': 'final_answer',
                'confidence': 1.0,
                'code_result': None
            })
            
            yield {
                "step": "FINAL",
                "thought": final_answer,
                "confidence": response.get("confidence", 0.9),
                "time_seconds": elapsed
            }
            break
            
        step += 1

# ────────────────────────────────────────────────────────────────
# ROTAS FLASK
# ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/mensagem", methods=["POST"])
async def handle_message():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    # O user_id é crucial para o banco de dados de memória funcionar por pessoa
    user_id = data.get("user_id", "default_user") 
    
    if not message:
        return jsonify({"error": "Nenhuma mensagem fornecida"}), 400
        
    steps = []
    async for step in agent_loop(user_id, message):
        steps.append(step)
    return jsonify({"steps": steps})

@app.route("/api/mensagem/stream", methods=["POST"])
async def stream_message():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    user_id = data.get("user_id", "default_user")
    
    if not message:
        return jsonify({"error": "Nenhuma mensagem fornecida"}), 400

    async def event_generator():
        async for step in agent_loop(user_id, message):
            yield f"data: {json.dumps(step, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(event_generator()),
        mimetype="text/event-stream"
    )

# ────────────────────────────────────────────────────────────────
# ROTA DE ADMINISTRAÇÃO DA MEMÓRIA
# ────────────────────────────────────────────────────────────────
@app.route("/api/admin/memoria/<user_id>", methods=["GET"])
def get_memory_stats(user_id):
    """
    Rota para verificar se o banco de dados está funcionando.
    Retorna estatísticas de memória do usuário.
    """
    try:
        stats = memory_agent.get_stats(user_id)
        return jsonify({
            "status": "success",
            "user_id": user_id,
            "database_file": mem_config.long_term_db,
            "stats": stats
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Garante que a pasta atual é o diretório de trabalho para criar o DB corretamente
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print(f"🚀 Bot iniciado. Banco de dados de memória em: {os.path.abspath(mem_config.long_term_db)}")
    app.run(host="0.0.0.0", port=5000, debug=True)
