# ============================================================
# OPENBOT v3.0 - ARQUITETURA PLUG & PLAY COM TOOL USE
# Core API com GROQ (openai==0.28.1) e 32 Ferramentas
# ============================================================

import os
import json
import time
import hashlib
import logging
import asyncio
import subprocess
import psutil
import re
import sqlite3
import aiohttp
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from quart import Quart, request, jsonify, Response

# ============================================================
# HGR MEMORY - 3 NÍVEIS
# ============================================================

try:
    from HGR import MemoryEnhancedAgent, MemoryConfig
    print("✅ HGR Memory (3 níveis) carregado com sucesso.")
except ImportError as e:
    print(f"❌ Erro ao importar HGR: {e}")
    exit(1)

# ============================================================
# AUTH SYSTEM - JWT
# ============================================================

try:
    from auth_system import (
        UserDatabase,
        AuthManager,
        require_auth,
        get_client_ip,
        cleanup_old_tokens
    )
    print("✅ Sistema de autenticação JWT carregado.")
except ImportError as e:
    print(f"❌ Erro ao importar auth_system: {e}")
    exit(1)

# ============================================================
# GROQ CONFIG (via openai 0.28.1)
# ============================================================

import openai

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

if not GROQ_API_KEY:
    print("⚠️ GROQ_API_KEY não definida!")
else:
    print(f"✅ GROQ_API_KEY carregada")

openai.api_key = GROQ_API_KEY
openai.api_base = "https://api.groq.com/openai/v1"
MODEL = "llama-3.1-8b-instant"

# ============================================================
# APP INIT
# ============================================================

app = Quart(__name__)

# Configurações
MAX_TOOL_EXECUTIONS = 32
MAX_AGENT_STEPS = 15
TOOL_TIMEOUT = 30

# Pools
thread_pool = ThreadPoolExecutor(max_workers=16)
process_pool = ProcessPoolExecutor(max_workers=4)

# Logging
logging.basicConfig(
    filename="openbot_v3.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ============================================================
# AUTH INIT
# ============================================================

user_db = UserDatabase("users.db")
auth_manager = AuthManager(user_db)
app.config["auth_manager"] = auth_manager
print("✅ Sistema JWT inicializado.")

# ============================================================
# MEMORY CONFIG
# ============================================================

mem_config = MemoryConfig(
    long_term_db="agent_memory_v3.db",
    short_term_size=20,
    importance_threshold=0.5
)

memory_agent = MemoryEnhancedAgent(mem_config)
print("✅ Memória HGR configurada.")

# ============================================================
# TOOL SYSTEM - 32 FERRAMENTAS PODEROSAS
# ============================================================

class ToolCategory(Enum):
    PYTHON = "python"
    SHELL = "shell"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    DATA = "data"
    SYSTEM = "system"
    CRYPTO = "crypto"
    UTILITY = "utility"

@dataclass
class Tool:
    name: str
    description: str
    category: ToolCategory
    function: Callable
    requires_sudo: bool = False
    timeout: int = 30
    dangerous: bool = False

class ToolRegistry:
    """Registro central de ferramentas"""
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self.tool_history: Dict[str, List[Dict]] = {}
        self._register_all_tools()
    
    def register(self, tool: Tool):
        self.tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)
    
    def list_tools(self) -> List[Dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category.value,
                "dangerous": t.dangerous
            }
            for t in self.tools.values()
        ]
    
    def _register_all_tools(self):
        """Registra todas as 32 ferramentas"""
        
        # ===== PYTHON TOOLS (1-5) =====
        
        async def execute_python(code: str) -> str:
            """Executa código Python arbitrário"""
            try:
                # Sandbox básico
                restricted_globals = {
                    '__builtins__': {
                        'print': print,
                        'len': len,
                        'range': range,
                        'int': int,
                        'str': str,
                        'float': float,
                        'list': list,
                        'dict': dict,
                        'set': set,
                        'tuple': tuple,
                        'enumerate': enumerate,
                        'zip': zip,
                        'map': map,
                        'filter': filter,
                        'sum': sum,
                        'max': max,
                        'min': min,
                        'abs': abs,
                        'round': round,
                        'sorted': sorted,
                        'reversed': reversed,
                        'any': any,
                        'all': all,
                        'open': None  # Bloqueado
                    }
                }
                
                local_vars = {}
                exec(code, restricted_globals, local_vars)
                return json.dumps(local_vars.get('result', 'Executado com sucesso'))
            except Exception as e:
                return f"Erro Python: {str(e)}"
        
        self.register(Tool(
            name="python_execute",
            description="Executa código Python arbitrário. Use 'result' para retornar valores.",
            category=ToolCategory.PYTHON,
            function=execute_python,
            dangerous=True
        ))
        
        async def python_eval(expression: str) -> str:
            """Avalia uma expressão Python"""
            try:
                result = eval(expression)
                return str(result)
            except Exception as e:
                return f"Erro: {str(e)}"
        
        self.register(Tool(
            name="python_eval",
            description="Avalia uma expressão Python simples",
            category=ToolCategory.PYTHON,
            function=python_eval
        ))
        
        async def python_import(module: str) -> str:
            """Importa e retorna informações de um módulo"""
            try:
                module_obj = __import__(module)
                functions = [f for f in dir(module_obj) if not f.startswith('_')]
                return f"Módulo {module} importado. Funções: {functions[:10]}"
            except Exception as e:
                return f"Erro ao importar: {str(e)}"
        
        self.register(Tool(
            name="python_import",
            description="Importa um módulo Python e lista suas funções",
            category=ToolCategory.PYTHON,
            function=python_import
        ))
        
        async def python_inspect(obj: str) -> str:
            """Inspeciona um objeto Python"""
            try:
                obj_eval = eval(obj)
                info = {
                    "type": str(type(obj_eval)),
                    "dir": dir(obj_eval)[:20],
                    "repr": repr(obj_eval)[:200]
                }
                return json.dumps(info)
            except Exception as e:
                return f"Erro: {str(e)}"
        
        self.register(Tool(
            name="python_inspect",
            description="Inspeciona um objeto Python (type, dir, repr)",
            category=ToolCategory.PYTHON,
            function=python_inspect
        ))
        
        async def python_debug(code: str) -> str:
            """Debuga código Python com traceback detalhado"""
            try:
                import traceback
                exec_globals = {}
                try:
                    exec(code, exec_globals)
                    return "Código executado sem erros"
                except Exception as e:
                    tb = traceback.format_exc()
                    return f"Erro: {str(e)}\nTraceback:\n{tb}"
            except Exception as e:
                return f"Erro no debug: {str(e)}"
        
        self.register(Tool(
            name="python_debug",
            description="Executa código Python com debug detalhado",
            category=ToolCategory.PYTHON,
            function=python_debug
        ))
        
        # ===== SHELL TOOLS (6-10) =====
        
        async def shell_execute(command: str) -> str:
            """Executa comando shell (com timeout)"""
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=TOOL_TIMEOUT,
                    env={**os.environ, 'PATH': '/usr/local/bin:/usr/bin:/bin'}
                )
                output = result.stdout.strip() or result.stderr.strip()
                return output or "Comando executado (sem output)"
            except subprocess.TimeoutExpired:
                return f"Timeout após {TOOL_TIMEOUT}s"
            except Exception as e:
                return f"Erro shell: {str(e)}"
        
        self.register(Tool(
            name="shell_execute",
            description="Executa comando shell (com segurança)",
            category=ToolCategory.SHELL,
            function=shell_execute,
            dangerous=True
        ))
        
        async def shell_script(script: str) -> str:
            """Executa um script shell multi-linha"""
            try:
                with open('/tmp/temp_script.sh', 'w') as f:
                    f.write("#!/bin/bash\n")
                    f.write(script)
                
                os.chmod('/tmp/temp_script.sh', 0o755)
                
                result = subprocess.run(
                    ['/bin/bash', '/tmp/temp_script.sh'],
                    capture_output=True,
                    text=True,
                    timeout=TOOL_TIMEOUT
                )
                
                os.remove('/tmp/temp_script.sh')
                
                return result.stdout.strip() or result.stderr.strip()
            except Exception as e:
                return f"Erro script: {str(e)}"
        
        self.register(Tool(
            name="shell_script",
            description="Executa script shell multi-linha",
            category=ToolCategory.SHELL,
            function=shell_script,
            dangerous=True
        ))
        
        async def shell_env() -> str:
            """Retorna variáveis de ambiente (seguras)"""
            safe_vars = ['PATH', 'HOME', 'USER', 'SHELL', 'PWD']
            env = {k: os.environ.get(k, '') for k in safe_vars}
            return json.dumps(env)
        
        self.register(Tool(
            name="shell_env",
            description="Lista variáveis de ambiente seguras",
            category=ToolCategory.SHELL,
            function=shell_env
        ))
        
        async def shell_process_list() -> str:
            """Lista processos em execução"""
            try:
                processes = []
                for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                    try:
                        processes.append(proc.info)
                    except:
                        pass
                return json.dumps(processes[:20])  # Limitar a 20
            except Exception as e:
                return f"Erro: {str(e)}"
        
        self.register(Tool(
            name="shell_process_list",
            description="Lista processos em execução",
            category=ToolCategory.SHELL,
            function=shell_process_list
        ))
        
        async def shell_kill_process(pid: int) -> str:
            """Mata um processo por PID"""
            try:
                process = psutil.Process(pid)
                process.terminate()
                return f"Processo {pid} terminado"
            except Exception as e:
                return f"Erro: {str(e)}"
        
        self.register(Tool(
            name="shell_kill_process",
            description="Termina um processo por PID",
            category=ToolCategory.SHELL,
            function=shell_kill_process,
            dangerous=True
        ))
        
        # ===== NETWORK TOOLS (11-16) =====
        
        async def curl_request(url: str, method: str = "GET", headers: Dict = None, data: str = None) -> str:
            """Faz requisição HTTP usando curl-like interface"""
            try:
                async with aiohttp.ClientSession() as session:
                    if method.upper() == "GET":
                        async with session.get(url, headers=headers or {}, timeout=TOOL_TIMEOUT) as resp:
                            text = await resp.text()
                            return f"Status: {resp.status}\nHeaders: {dict(resp.headers)}\nBody: {text[:500]}"
                    else:
                        async with session.post(url, headers=headers or {}, data=data, timeout=TOOL_TIMEOUT) as resp:
                            text = await resp.text()
                            return f"Status: {resp.status}\nHeaders: {dict(resp.headers)}\nBody: {text[:500]}"
            except Exception as e:
                return f"Erro curl: {str(e)}"
        
        self.register(Tool(
            name="curl_request",
            description="Faz requisições HTTP (GET/POST) com headers e body",
            category=ToolCategory.NETWORK,
            function=curl_request
        ))
        
        async def http_download(url: str, filename: str = None) -> str:
            """Download de arquivo via HTTP"""
            try:
                if not filename:
                    filename = url.split('/')[-1] or 'downloaded_file'
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=TOOL_TIMEOUT) as resp:
                        content = await resp.read()
                        with open(f"/tmp/{filename}", 'wb') as f:
                            f.write(content)
                        return f"Downloaded {len(content)} bytes to /tmp/{filename}"
            except Exception as e:
                return f"Erro download: {str(e)}"
        
        self.register(Tool(
            name="http_download",
            description="Download de arquivos via HTTP",
            category=ToolCategory.NETWORK,
            function=http_download
        ))
        
        async def ping_host(host: str, count: int = 4) -> str:
            """Ping a host"""
            try:
                result = subprocess.run(
                    ['ping', '-c', str(count), host],
                    capture_output=True,
                    text=True,
                    timeout=TOOL_TIMEOUT
                )
                return result.stdout or result.stderr
            except Exception as e:
                return f"Erro ping: {str(e)}"
        
        self.register(Tool(
            name="ping_host",
            description="Pinga um host para testar conectividade",
            category=ToolCategory.NETWORK,
            function=ping_host
        ))
        
        async def dns_lookup(domain: str) -> str:
            """DNS lookup"""
            try:
                import socket
                ip = socket.gethostbyname(domain)
                return f"{domain} -> {ip}"
            except Exception as e:
                return f"Erro DNS: {str(e)}"
        
        self.register(Tool(
            name="dns_lookup",
            description="Resolve DNS de um domínio",
            category=ToolCategory.NETWORK,
            function=dns_lookup
        ))
        
        async def port_scan(host: str, ports: str) -> str:
            """Scan de portas simples"""
            try:
                import socket
                port_list = [int(p) for p in ports.split(',')]
                open_ports = []
                
                for port in port_list[:10]:  # Limitar a 10 portas
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex((host, port))
                    if result == 0:
                        open_ports.append(port)
                    sock.close()
                
                return f"Portas abertas em {host}: {open_ports}"
            except Exception as e:
                return f"Erro scan: {str(e)}"
        
        self.register(Tool(
            name="port_scan",
            description="Scan básico de portas (formato: '80,443,8080')",
            category=ToolCategory.NETWORK,
            function=port_scan
        ))
        
        async def whois_lookup(domain: str) -> str:
            """Whois lookup"""
            try:
                result = subprocess.run(
                    ['whois', domain],
                    capture_output=True,
                    text=True,
                    timeout=TOOL_TIMEOUT
                )
                return result.stdout[:1000] or result.stderr
            except Exception as e:
                return f"Erro whois: {str(e)}"
        
        self.register(Tool(
            name="whois_lookup",
            description="Consulta WHOIS de domínio",
            category=ToolCategory.NETWORK,
            function=whois_lookup
        ))
        
        # ===== FILESYSTEM TOOLS (17-21) =====
        
        async def file_read(path: str) -> str:
            """Lê conteúdo de arquivo"""
            try:
                if not path.startswith('/tmp/'):
                    return "Acesso negado: apenas /tmp/ é permitido"
                
                with open(path, 'r') as f:
                    content = f.read()
                return content[:2000]  # Limitar tamanho
            except Exception as e:
                return f"Erro leitura: {str(e)}"
        
        self.register(Tool(
            name="file_read",
            description="Lê arquivo (apenas /tmp/)",
            category=ToolCategory.FILESYSTEM,
            function=file_read
        ))
        
        async def file_write(path: str, content: str) -> str:
            """Escreve conteúdo em arquivo"""
            try:
                if not path.startswith('/tmp/'):
                    return "Acesso negado: apenas /tmp/ é permitido"
                
                with open(path, 'w') as f:
                    f.write(content)
                return f"Arquivo {path} escrito com sucesso"
            except Exception as e:
                return f"Erro escrita: {str(e)}"
        
        self.register(Tool(
            name="file_write",
            description="Escreve em arquivo (apenas /tmp/)",
            category=ToolCategory.FILESYSTEM,
            function=file_write
        ))
        
        async def file_list(path: str = '/tmp') -> str:
            """Lista arquivos em diretório"""
            try:
                files = os.listdir(path)
                return json.dumps(files[:50])  # Limitar a 50
            except Exception as e:
                return f"Erro listagem: {str(e)}"
        
        self.register(Tool(
            name="file_list",
            description="Lista arquivos em diretório",
            category=ToolCategory.FILESYSTEM,
            function=file_list
        ))
        
        async def file_delete(path: str) -> str:
            """Deleta arquivo"""
            try:
                if not path.startswith('/tmp/'):
                    return "Acesso negado: apenas /tmp/ é permitido"
                
                os.remove(path)
                return f"Arquivo {path} deletado"
            except Exception as e:
                return f"Erro deleção: {str(e)}"
        
        self.register(Tool(
            name="file_delete",
            description="Deleta arquivo (apenas /tmp/)",
            category=ToolCategory.FILESYSTEM,
            function=file_delete,
            dangerous=True
        ))
        
        async def file_info(path: str) -> str:
            """Informações detalhadas de arquivo"""
            try:
                stat = os.stat(path)
                info = {
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "permissions": oct(stat.st_mode)[-3:]
                }
                return json.dumps(info)
            except Exception as e:
                return f"Erro info: {str(e)}"
        
        self.register(Tool(
            name="file_info",
            description="Informações detalhadas de arquivo",
            category=ToolCategory.FILESYSTEM,
            function=file_info
        ))
        
        # ===== DATA TOOLS (22-25) =====
        
        async def data_parse_json(json_str: str) -> str:
            """Parse e valida JSON"""
            try:
                data = json.loads(json_str)
                return json.dumps(data, indent=2, ensure_ascii=False)
            except Exception as e:
                return f"Erro parse JSON: {str(e)}"
        
        self.register(Tool(
            name="data_parse_json",
            description="Parse e valida JSON",
            category=ToolCategory.DATA,
            function=data_parse_json
        ))
        
        async def data_query_json(json_str: str, query: str) -> str:
            """Query em JSON usando JMESPath"""
            try:
                import jmespath
                data = json.loads(json_str)
                result = jmespath.search(query, data)
                return json.dumps(result, indent=2, ensure_ascii=False)
            except ImportError:
                return "JMESPath não instalado"
            except Exception as e:
                return f"Erro query: {str(e)}"
        
        self.register(Tool(
            name="data_query_json",
            description="Query em JSON com JMESPath",
            category=ToolCategory.DATA,
            function=data_query_json
        ))
        
        async def data_csv_to_json(csv_str: str) -> str:
            """Converte CSV para JSON"""
            try:
                import csv
                from io import StringIO
                
                reader = csv.DictReader(StringIO(csv_str))
                data = list(reader)
                return json.dumps(data, indent=2, ensure_ascii=False)
            except Exception as e:
                return f"Erro conversão: {str(e)}"
        
        self.register(Tool(
            name="data_csv_to_json",
            description="Converte CSV para JSON",
            category=ToolCategory.DATA,
            function=data_csv_to_json
        ))
        
        async def data_sqlite_query(db_path: str, query: str) -> str:
            """Executa query SQLite em banco"""
            try:
                if not db_path.startswith('/tmp/'):
                    return "Acesso negado: apenas /tmp/ é permitido"
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute(query)
                
                if query.strip().upper().startswith('SELECT'):
                    rows = cursor.fetchall()
                    columns = [description[0] for description in cursor.description]
                    result = [dict(zip(columns, row)) for row in rows]
                    return json.dumps(result, indent=2, ensure_ascii=False)
                else:
                    conn.commit()
                    return f"Query executada. Rows affected: {cursor.rowcount}"
                
                conn.close()
            except Exception as e:
                return f"Erro SQLite: {str(e)}"
        
        self.register(Tool(
            name="data_sqlite_query",
            description="Executa query SQLite em banco",
            category=ToolCategory.DATA,
            function=data_sqlite_query
        ))
        
        # ===== SYSTEM TOOLS (26-28) =====
        
        async def system_info() -> str:
            """Informações do sistema"""
            try:
                info = {
                    "hostname": os.uname().nodename,
                    "system": os.uname().sysname,
                    "release": os.uname().release,
                    "cpu_count": psutil.cpu_count(),
                    "cpu_percent": psutil.cpu_percent(interval=1),
                    "memory": psutil.virtual_memory()._asdict(),
                    "disk": psutil.disk_usage('/')._asdict()
                }
                # Converter bytes para MB/GB legível
                for k in ['memory', 'disk']:
                    if k in info:
                        for sk in ['total', 'available', 'used', 'free']:
                            if sk in info[k]:
                                info[k][sk] = f"{info[k][sk] / (1024**3):.2f} GB"
                
                return json.dumps(info, indent=2, default=str)
            except Exception as e:
                return f"Erro info sistema: {str(e)}"
        
        self.register(Tool(
            name="system_info",
            description="Informações detalhadas do sistema",
            category=ToolCategory.SYSTEM,
            function=system_info
        ))
        
        async def system_time() -> str:
            """Data e hora do sistema"""
            now = datetime.now()
            return {
                "iso": now.isoformat(),
                "timestamp": now.timestamp(),
                "formatted": now.strftime("%Y-%m-%d %H:%M:%S")
            }
        
        self.register(Tool(
            name="system_time",
            description="Data e hora atual",
            category=ToolCategory.SYSTEM,
            function=system_time
        ))
        
        async def system_uptime() -> str:
            """Tempo de atividade do sistema"""
            uptime_seconds = time.time() - psutil.boot_time()
            uptime = str(timedelta(seconds=uptime_seconds))
            return f"Sistema ativo há {uptime}"
        
        self.register(Tool(
            name="system_uptime",
            description="Tempo de atividade do sistema",
            category=ToolCategory.SYSTEM,
            function=system_uptime
        ))
        
        # ===== CRYPTO TOOLS (29-30) =====
        
        async def crypto_hash(text: str, algorithm: str = "sha256") -> str:
            """Gera hash de texto"""
            try:
                if algorithm == "md5":
                    result = hashlib.md5(text.encode()).hexdigest()
                elif algorithm == "sha1":
                    result = hashlib.sha1(text.encode()).hexdigest()
                elif algorithm == "sha256":
                    result = hashlib.sha256(text.encode()).hexdigest()
                else:
                    return f"Algoritmo não suportado: {algorithm}"
                
                return f"{algorithm}: {result}"
            except Exception as e:
                return f"Erro hash: {str(e)}"
        
        self.register(Tool(
            name="crypto_hash",
            description="Gera hash (md5, sha1, sha256)",
            category=ToolCategory.CRYPTO,
            function=crypto_hash
        ))
        
        async def crypto_random(length: int = 16) -> str:
            """Gera string aleatória"""
            import secrets
            import string
            
            alphabet = string.ascii_letters + string.digits
            result = ''.join(secrets.choice(alphabet) for _ in range(length))
            return result
        
        self.register(Tool(
            name="crypto_random",
            description="Gera string aleatória segura",
            category=ToolCategory.CRYPTO,
            function=crypto_random
        ))
        
        # ===== UTILITY TOOLS (31-32) =====
        
        async def util_calc(expression: str) -> str:
            """Calculadora simples"""
            try:
                # Avaliação segura (apenas expressões matemáticas)
                allowed_chars = set("0123456789+-*/(). ")
                if not all(c in allowed_chars for c in expression):
                    return "Expressão contém caracteres não permitidos"
                
                result = eval(expression, {"__builtins__": {}}, {})
                return f"{expression} = {result}"
            except Exception as e:
                return f"Erro cálculo: {str(e)}"
        
        self.register(Tool(
            name="util_calc",
            description="Calculadora matemática simples",
            category=ToolCategory.UTILITY,
            function=util_calc
        ))
        
        async def util_uuid() -> str:
            """Gera UUID"""
            import uuid
            return str(uuid.uuid4())
        
        self.register(Tool(
            name="util_uuid",
            description="Gera UUID único",
            category=ToolCategory.UTILITY,
            function=util_uuid
        ))
        
        async def util_base64_encode(text: str) -> str:
            """Codifica em base64"""
            import base64
            return base64.b64encode(text.encode()).decode()
        
        self.register(Tool(
            name="util_base64_encode",
            description="Codifica texto em base64",
            category=ToolCategory.UTILITY,
            function=util_base64_encode
        ))
        
        async def util_base64_decode(encoded: str) -> str:
            """Decodifica base64"""
            import base64
            try:
                return base64.b64decode(encoded).decode()
            except Exception as e:
                return f"Erro decode: {str(e)}"
        
        self.register(Tool(
            name="util_base64_decode",
            description="Decodifica base64",
            category=ToolCategory.UTILITY,
            function=util_base64_decode
        ))

# ============================================================
# TOOL EXECUTION ENGINE
# ============================================================

class ToolExecutionEngine:
    """Motor de execução de ferramentas com cache e controle"""
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.execution_history: Dict[str, List[Dict]] = {}
        self.cache: Dict[str, Any] = {}
        self.cache_ttl: Dict[str, datetime] = {}
    
    def get_cache_key(self, tool_name: str, *args, **kwargs) -> str:
        """Gera chave de cache"""
        key_parts = [tool_name] + [str(a) for a in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
        return hashlib.sha256("|".join(key_parts).encode()).hexdigest()
    
    async def execute(self, tool_name: str, user_id: str, *args, **kwargs) -> Dict:
        """Executa uma ferramenta com cache e logging"""
        
        start_time = time.time()
        
        # Verificar cache
        cache_key = self.get_cache_key(tool_name, *args, **kwargs)
        if cache_key in self.cache:
            cache_time = self.cache_ttl.get(cache_key)
            if cache_time and datetime.now() < cache_time:
                return {
                    "tool": tool_name,
                    "cached": True,
                    "result": self.cache[cache_key],
                    "time": 0
                }
        
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return {
                "tool": tool_name,
                "error": f"Ferramenta '{tool_name}' não encontrada",
                "time": time.time() - start_time
            }
        
        try:
            # Executar ferramenta
            if asyncio.iscoroutinefunction(tool.function):
                result = await tool.function(*args, **kwargs)
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    thread_pool,
                    tool.function,
                    *args, **kwargs
                )
            
            # Guardar em cache (apenas para resultados não-dangereos)
            if not tool.dangerous:
                self.cache[cache_key] = result
                self.cache_ttl[cache_key] = datetime.now() + timedelta(minutes=5)
            
            # Registrar histórico
            if user_id not in self.execution_history:
                self.execution_history[user_id] = []
            
            self.execution_history[user_id].append({
                "tool": tool_name,
                "args": args,
                "kwargs": kwargs,
                "time": time.time() - start_time,
                "timestamp": datetime.now().isoformat()
            })
            
            # Manter apenas últimos 100
            self.execution_history[user_id] = self.execution_history[user_id][-100:]
            
            return {
                "tool": tool_name,
                "result": result,
                "time": round(time.time() - start_time, 3)
            }
            
        except Exception as e:
            logging.error(f"Erro executando {tool_name}: {e}")
            return {
                "tool": tool_name,
                "error": str(e),
                "time": round(time.time() - start_time, 3)
            }

# ============================================================
# RESOURCE MONITOR
# ============================================================

def get_resource_usage():
    try:
        process = psutil.Process()
        cpu = psutil.cpu_percent(interval=0.1)
        mem = process.memory_info().rss / (1024 * 1024)
        return round(cpu, 1), round(mem, 1)
    except:
        return 0.0, 0.0

# ============================================================
# AGENT - WITH TOOL USE
# ============================================================

SYSTEM_PROMPT = """Você é o OPENBOT v3.0, um assistente avançado com 32 ferramentas disponíveis.

CAPACIDADES PRINCIPAIS:
- Raciocínio estruturado e execução de tarefas complexas
- Uso de ferramentas para Python, Shell, Network, Filesystem
- Memória persistente de 3 níveis (curto/longo prazo + relevância)
- Execução segura em ambiente isolado

FERRAMENTAS DISPONÍVEIS:
{tools_description}

FORMATO DE RESPOSTA:
Para usar ferramentas, responda com:
<tool>
{{
    "name": "nome_da_ferramenta",
    "args": [arg1, arg2],
    "kwargs": {{"key": "value"}}
}}
</tool>

O resultado da ferramenta será automaticamente processado e você poderá continuar a conversa.

Exemplo:
Usuário: "Qual o IP do google.com?"
Agente: <tool>
{{
    "name": "dns_lookup",
    "args": ["google.com"]
}}
</tool>

[Resultado da ferramenta: google.com -> 142.250.185.46]
O IP do Google é 142.250.185.46.

Seja natural, amigável e eficiente em português.
"""

# Inicializar registro de ferramentas
tool_registry = ToolRegistry()
tool_engine = ToolExecutionEngine(tool_registry)

async def agent_loop(user_id: str, user_query: str):
    """
    Loop principal do agente com ferramentas
    """
    
    # Gerar descrição das ferramentas para o prompt
    tools_description = "\n".join([
        f"- {t['name']}: {t['description']} (Categoria: {t['category']})"
        for t in tool_registry.list_tools()
    ])
    
    # Enhanced prompt com memória
    enhanced_prompt = memory_agent.get_enhanced_system_prompt(
        user_id, 
        user_query, 
        SYSTEM_PROMPT.format(tools_description=tools_description)
    )
    
    messages = [
        {"role": "system", "content": enhanced_prompt},
        {"role": "user", "content": user_query}
    ]
    
    step = 0
    tool_counter = 0
    
    while step < MAX_AGENT_STEPS and tool_counter < MAX_TOOL_EXECUTIONS:
        step += 1
        
        start = time.time()
        response_text = await async_llm(messages)
        elapsed = round(time.time() - start, 2)
        
        # Verificar se há chamada de ferramenta
        tool_match = re.search(r'<tool>(.*?)</tool>', response_text, re.DOTALL)
        
        if tool_match:
            try:
                tool_call = json.loads(tool_match.group(1).strip())
                tool_name = tool_call.get("name")
                args = tool_call.get("args", [])
                kwargs = tool_call.get("kwargs", {})
                
                # Executar ferramenta
                tool_result = await tool_engine.execute(
                    tool_name, 
                    user_id,
                    *args, 
                    **kwargs
                )
                
                tool_counter += 1
                
                # Adicionar resultado à conversa
                messages.append({"role": "assistant", "content": response_text})
                messages.append({
                    "role": "system", 
                    "content": f"Resultado da ferramenta {tool_name}: {json.dumps(tool_result, ensure_ascii=False)}"
                })
                
                # Registrar na memória
                memory_agent.record_step(user_id, user_query, {
                    "step": step,
                    "thought": response_text[:100],
                    "tool": tool_name,
                    "result": tool_result
                })
                
                # Continuar loop para próxima iteração
                continue
                
            except json.JSONDecodeError as e:
                error_msg = f"Erro ao parsear chamada de ferramenta: {e}"
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "system", "content": error_msg})
                continue
        
        # Se não há chamada de ferramenta, é a resposta final
        memory_agent.record_step(user_id, user_query, {
            "steps": step,
            "tools_used": tool_counter,
            "final_response": response_text[:200]
        })
        
        yield {
            "type": "final",
            "response": response_text,
            "tools_used": tool_counter,
            "steps": step,
            "time": elapsed
        }
        break

# ============================================================
# GROQ CALL
# ============================================================

def sync_llm(messages):
    """Chamada síncrona à GROQ"""
    try:
        response = openai.ChatCompletion.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=2048
        )
        return response
    except Exception as e:
        logging.error(f"Erro GROQ: {e}")
        raise

async def async_llm(messages):
    """Chamada assíncrona à GROQ"""
    loop = asyncio.get_running_loop()
    try:
        response = await loop.run_in_executor(
            thread_pool,
            lambda: sync_llm(messages)
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Erro: {str(e)[:100]}"

# ============================================================
# API REST ENDPOINTS
# ============================================================

@app.route("/")
async def index():
    """Status da API"""
    cpu, mem = get_resource_usage()
    
    return jsonify({
        "name": "OPENBOT v3.0",
        "status": "online",
        "architecture": "Plug & Play com Tool Use",
        "layers": {
            "auth": "JWT Authentication",
            "agent": "Tool-based Reasoning (32 ferramentas)",
            "memory": "HGR 3 Níveis"
        },
        "model": MODEL,
        "resources": {
            "cpu": f"{cpu}%",
            "memory": f"{mem}MB"
        },
        "tools": {
            "total": len(tool_registry.list_tools()),
            "categories": [c.value for c in ToolCategory],
            "list": tool_registry.list_tools()[:10]  # Primeiras 10
        },
        "endpoints": {
            "public": [
                "POST /api/auth/register",
                "POST /api/auth/login"
            ],
            "protected": [
                "POST /api/chat",
                "POST /api/chat/stream",
                "GET /api/user/profile",
                "GET /api/tools/list",
                "GET /api/tools/execute/{name}",
                "GET /api/tools/history",
                "POST /api/auth/logout",
                "GET /api/admin/stats"
            ]
        }
    })

@app.route("/api/tools/list", methods=["GET"])
@require_auth()
async def list_tools():
    """Lista todas as ferramentas disponíveis"""
    tools = tool_registry.list_tools()
    return jsonify({
        "status": "success",
        "total": len(tools),
        "tools": tools
    })

@app.route("/api/tools/execute/<tool_name>", methods=["POST"])
@require_auth()
async def execute_tool(tool_name):
    """Executa uma ferramenta específica"""
    user_data = request.user_data
    data = await request.get_json()
    
    args = data.get("args", [])
    kwargs = data.get("kwargs", {})
    
    result = await tool_engine.execute(tool_name, user_data['username'], *args, **kwargs)
    
    return jsonify({
        "status": "success",
        "user": user_data['username'],
        "result": result
    })

@app.route("/api/tools/history", methods=["GET"])
@require_auth()
async def tool_history():
    """Histórico de execução de ferramentas do usuário"""
    user_data = request.user_data
    history = tool_engine.execution_history.get(user_data['username'], [])
    
    return jsonify({
        "status": "success",
        "history": history[-50:]  # Últimas 50
    })

# ============================================================
# AUTH ENDPOINTS
# ============================================================

@app.route("/api/auth/register", methods=["POST"])
async def register():
    """Registro de novo usuário"""
    data = await request.get_json()
    
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    
    if not all([username, email, password]):
        return jsonify({"error": "Campos obrigatórios"}), 400
    
    success, message, user_data = auth_manager.register_user(
        username, email, password
    )
    
    if success:
        return jsonify({
            "status": "success",
            "message": message,
            "user": user_data
        }), 201
    else:
        return jsonify({"error": message}), 400

@app.route("/api/auth/login", methods=["POST"])
async def login():
    """Login JWT"""
    data = await request.get_json()
    
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    if not all([username, password]):
        return jsonify({"error": "Campos obrigatórios"}), 400
    
    ip_address = get_client_ip(request)
    
    success, message, token = auth_manager.login(
        username, password, ip_address
    )
    
    if success:
        return jsonify({
            "status": "success",
            "message": message,
            "token": token,
            "expires": "24h"
        }), 200
    else:
        return jsonify({"error": message}), 401

@app.route("/api/auth/logout", methods=["POST"])
@require_auth()
async def logout():
    """Logout - revoga token"""
    auth_header = request.headers.get('Authorization')
    token = auth_header.split(' ')[1]
    
    auth_manager.revoke_token(token)
    
    return jsonify({"status": "success", "message": "Logout realizado"}), 200

# ============================================================
# PROTECTED ENDPOINTS
# ============================================================

@app.route("/api/user/profile", methods=["GET"])
@require_auth()
async def get_profile():
    """Perfil do usuário"""
    user_data = request.user_data
    
    # Buscar estatísticas de memória
    try:
        stats = memory_agent.get_stats(user_data['username'])
    except:
        stats = {"error": "Memória indisponível"}
    
    # Estatísticas de ferramentas
    tool_stats = {
        "total_executions": len(tool_engine.execution_history.get(user_data['username'], [])),
        "recent_tools": [
            {
                "tool": h['tool'],
                "time": h['time'],
                "timestamp": h['timestamp']
            }
            for h in tool_engine.execution_history.get(user_data['username'], [])[-5:]
        ]
    }
    
    return jsonify({
        "status": "success",
        "user": {
            "user_id": user_data['user_id'],
            "username": user_data['username'],
            "email": user_data['email'],
            "is_admin": user_data.get('is_admin', False)
        },
        "memory_stats": stats,
        "tool_stats": tool_stats
    })

@app.route("/api/chat", methods=["POST"])
@require_auth()
async def chat():
    """Chat com resposta completa"""
    user_data = request.user_data
    data = await request.get_json()
    
    message = data.get("message", "").strip()
    
    if not message:
        return jsonify({"error": "Mensagem vazia"}), 400
    
    responses = []
    async for response in agent_loop(user_data['username'], message):
        responses.append(response)
    
    return jsonify({
        "status": "success",
        "user": user_data['username'],
        "responses": responses
    })

@app.route("/api/chat/stream", methods=["POST"])
@require_auth()
async def chat_stream():
    """Chat com streaming SSE"""
    user_data = request.user_data
    data = await request.get_json()
    
    message = data.get("message", "").strip()
    
    if not message:
        return jsonify({"error": "Mensagem vazia"}), 400
    
    async def event_stream():
        async for response in agent_loop(user_data['username'], message):
            yield f"data: {json.dumps(response, ensure_ascii=False)}\n\n"
    
    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/api/admin/stats", methods=["GET"])
@require_auth(admin_only=True)
async def admin_stats():
    """Estatísticas do sistema (admin)"""
    
    # Recursos
    cpu, mem = get_resource_usage()
    
    # Tamanho dos bancos
    db_sizes = {}
    for db in ["users.db", "agent_memory_v3.db", "openbot_v3.log"]:
        try:
            size = os.path.getsize(db) / (1024 * 1024)  # MB
            db_sizes[db] = f"{size:.2f} MB"
        except:
            db_sizes[db] = "N/A"
    
    # Estatísticas de ferramentas
    all_executions = []
    for user, history in tool_engine.execution_history.items():
        all_executions.extend(history)
    
    tool_usage = {}
    for exec in all_executions:
        tool = exec['tool']
        tool_usage[tool] = tool_usage.get(tool, 0) + 1
    
    return jsonify({
        "status": "success",
        "system": {
            "model": MODEL,
            "resources": {
                "cpu": f"{cpu}%",
                "memory": f"{mem}MB"
            },
            "databases": db_sizes,
            "cache": {
                "tool_cache": len(tool_engine.cache),
                "thread_pool": thread_pool._max_workers,
                "process_pool": process_pool._max_workers
            }
        },
        "tools": {
            "total_executions": len(all_executions),
            "unique_users": len(tool_engine.execution_history),
            "usage": tool_usage,
            "available": len(tool_registry.list_tools())
        }
    })

# ============================================================
# MAINTENANCE TASKS
# ============================================================

async def cleanup_task():
    """Limpeza periódica"""
    while True:
        await asyncio.sleep(3600)  # 1 hora
        
        try:
            # Limpar tokens
            deleted = cleanup_old_tokens(user_db, days=7)
            if deleted > 0:
                logging.info(f"Tokens removidos: {deleted}")
            
            # Limpar cache de ferramentas antigo
            now = datetime.now()
            expired_keys = []
            for key, expiry in tool_engine.cache_ttl.items():
                if now > expiry:
                    expired_keys.append(key)
            
            for key in expired_keys:
                if key in tool_engine.cache:
                    del tool_engine.cache[key]
                if key in tool_engine.cache_ttl:
                    del tool_engine.cache_ttl[key]
            
            if expired_keys:
                logging.info(f"Cache limpo: {len(expired_keys)} itens")
            
        except Exception as e:
            logging.error(f"Erro na limpeza: {e}")

@app.before_serving
async def startup():
    """Inicialização"""
    # Tarefa de limpeza
    asyncio.create_task(cleanup_task())
    
    # Testar GROQ
    try:
        test = await async_llm([{"role": "user", "content": "teste"}])
        print(f"✅ GROQ conectado: {test[:50]}...")
    except Exception as e:
        print(f"⚠️ GROQ: {e}")
    
    # Banner
    print("\n" + "="*70)
    print("🚀 OPENBOT v3.0 - ARQUITETURA PLUG & PLAY COM TOOL USE")
    print("="*70)
    print("📦 CAMADA DE FERRAMENTAS (32):")
    print("   • Python     (5)  • Shell    (5)  • Network  (6)")
    print("   • Filesystem (5)  • Data     (4)  • System   (3)")
    print("   • Crypto     (2)  • Utility  (4)")
    print("-"*70)
    print("🔧 CORE API:")
    print("   • AUTH    - JWT Authentication")
    print("   • AGENT   - Tool-based Reasoning")
    print("   • MEMORY  - HGR 3 Níveis")
    print("   • CACHE   - Tool Result Caching")
    print("-"*70)
    print("💾 DATABASES:")
    print("   • users.db            - Dados dos usuários")
    print("   • agent_memory_v3.db  - Memória persistente")
    print("-"*70)
    print("⚡ Plug & Play com Tool Use:")
    print("   • 32 ferramentas integradas")
    print("   • Cache inteligente (5 min TTL)")
    print("   • Execução segura em sandbox")
    print("   • Histórico por usuário")
    print("   • Streaming em tempo real")
    print("="*70)
    print(f"🌐 http://0.0.0.0:5000")
    print(f"🔧 Total de ferramentas: {len(tool_registry.list_tools())}")
    print("="*70)
    
    # Listar categorias
    for category in ToolCategory:
        tools_in_cat = [t for t in tool_registry.list_tools() if t['category'] == category.value]
        print(f"   {category.value.upper()}: {len(tools_in_cat)} ferramentas")
    
    print("="*70)

# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config

    config = Config()
    config.bind = ["0.0.0.0:5000"]
    config.use_reloader = False
    config.accesslog = "-"
    config.errorlog = "-"

    asyncio.run(hypercorn.asyncio.serve(app, config))