# ============================================================
# OPENBOT v3.0 - ARQUITETURA PLUG & PLAY COM TOOL USE
# Core API com GROQ (openai==0.28.1) e 40 Ferramentas (32 + 8 Memória)
# Diretório base: /sdcard/Download/acoude_ide/openbot_v2
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
# DIREtóRIO BASE (SDCARD)
# ============================================================

BASE_DIR = "/sdcard/Download/acoude_ide/WORKS"
os.makedirs(BASE_DIR, exist_ok=True)  # Garante que o diretório exista
os.makedirs(os.path.join(BASE_DIR, "exports"), exist_ok=True)  # Para exports de memória

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

GROQ_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()

if not GROQ_API_KEY:
    print("⚠️ GROQ_API_KEY não definida!")
else:
    print(f"✅ GROQ_API_KEY carregada")

openai.api_key = GROQ_API_KEY
openai.api_base = "https://api.deepseek.com/v1" 
MODEL = "deepseek-chat"

# ============================================================
# APP INIT
# ============================================================

app = Quart(__name__)

# Configurações
MAX_TOOL_EXECUTIONS = 40  # Aumentado para comportar novas tools
MAX_AGENT_STEPS = 16
TOOL_TIMEOUT = 900

# Pools
thread_pool = ThreadPoolExecutor(max_workers=16)
process_pool = ProcessPoolExecutor(max_workers=8)

# Logging (agora dentro do BASE_DIR)
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "openbot_v3.log"),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ============================================================
# AUTH INIT (bancos dentro do BASE_DIR)
# ============================================================

user_db = UserDatabase(os.path.join(BASE_DIR, "users.db"))
auth_manager = AuthManager(user_db)
app.config["auth_manager"] = auth_manager
print("✅ Sistema JWT inicializado.")

# ============================================================
# MEMORY CONFIG (banco dentro do BASE_DIR)
# ============================================================

mem_config = MemoryConfig(
    long_term_db=os.path.join(BASE_DIR, "agent_memory_v3.db"),
    short_term_size=20,
    importance_threshold=0.5
)

memory_agent = MemoryEnhancedAgent(mem_config)
print("✅ Memória HGR configurada.")

# ============================================================
# MEMORYSQL - SISTEMA DE MEMÓRIA PERSISTENTE
# ============================================================

class MemorySQL:
    """Classe para manipulação da memória HGR persistente"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(BASE_DIR, "agent_memory_v3.db")
        self._init_db()
    
    def _init_db(self):
        """Inicializa o banco se necessário"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Tabela principal de memórias
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    importance REAL DEFAULT 0.0,
                    access_count INTEGER DEFAULT 1,
                    last_accessed TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    category TEXT DEFAULT 'general',
                    tags TEXT,
                    expiry TIMESTAMP,
                    UNIQUE(user_id, key)
                )
            """)
            
            # Índices para performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user ON memories(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_importance ON memories(importance DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_category ON memories(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_expiry ON memories(expiry)")
            
            # Tabela de histórico de acessos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_access_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id INTEGER,
                    user_id TEXT,
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    context TEXT,
                    FOREIGN KEY(memory_id) REFERENCES memories(id)
                )
            """)
            
            conn.commit()
    
    # ============================================================
    # TOOL 1: memory_store - Armazenar memória
    # ============================================================
    
    async def memory_store(self, 
                          user_id: str, 
                          key: str, 
                          value: Any, 
                          importance: float = 0.5,
                          category: str = "general",
                          tags: List[str] = None,
                          expiry_days: Optional[int] = None) -> Dict:
        """
        Armazena uma memória no banco HGR
        """
        try:
            # Converte value para JSON se necessário
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            
            # Calcula expiry se fornecido
            expiry = None
            if expiry_days:
                expiry = (datetime.now() + timedelta(days=expiry_days)).isoformat()
            
            # Tags como JSON
            tags_json = json.dumps(tags) if tags else None
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # UPSERT: insere ou atualiza
                cursor.execute("""
                    INSERT INTO memories 
                    (user_id, key, value, importance, category, tags, expiry, last_accessed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, key) DO UPDATE SET
                        value = excluded.value,
                        importance = excluded.importance,
                        category = excluded.category,
                        tags = excluded.tags,
                        expiry = excluded.expiry,
                        last_accessed = CURRENT_TIMESTAMP,
                        access_count = access_count + 1
                """, (user_id, key, value, importance, category, tags_json, expiry, datetime.now().isoformat()))
                
                conn.commit()
                
                return {
                    "status": "success",
                    "operation": "store",
                    "user_id": user_id,
                    "key": key,
                    "importance": importance,
                    "expiry": expiry
                }
                
        except Exception as e:
            return {
                "status": "error",
                "operation": "store",
                "error": str(e)
            }
    
    # ============================================================
    # TOOL 2: memory_recall - Recuperar memória
    # ============================================================
    
    async def memory_recall(self, 
                           user_id: str, 
                           key: str = None,
                           category: str = None,
                           tags: List[str] = None,
                           min_importance: float = 0.0,
                           limit: int = 10,
                           include_expired: bool = False) -> Dict:
        """
        Recupera memórias do banco HGR
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Constrói query dinamicamente
                query = "SELECT * FROM memories WHERE user_id = ?"
                params = [user_id]
                
                if key:
                    query += " AND key = ?"
                    params.append(key)
                
                if category:
                    query += " AND category = ?"
                    params.append(category)
                
                if tags:
                    # Busca por tags (JSON contains)
                    placeholders = ','.join(['?'] * len(tags))
                    query += f" AND EXISTS (SELECT 1 FROM json_each(tags) WHERE json_each.value IN ({placeholders}))"
                    params.extend(tags)
                
                query += " AND importance >= ?"
                params.append(min_importance)
                
                if not include_expired:
                    query += " AND (expiry IS NULL OR expiry > datetime('now'))"
                
                query += " ORDER BY importance DESC, last_accessed DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                # Converte para lista de dicionários
                memories = []
                for row in rows:
                    memory = dict(row)
                    # Parse tags de volta pra lista
                    if memory['tags']:
                        memory['tags'] = json.loads(memory['tags'])
                    
                    # Tenta parse do value como JSON
                    try:
                        memory['value'] = json.loads(memory['value'])
                    except:
                        pass  # Mantém como string
                    
                    memories.append(memory)
                    
                    # Atualiza último acesso
                    cursor.execute("""
                        UPDATE memories SET last_accessed = ? 
                        WHERE id = ?
                    """, (datetime.now().isoformat(), memory['id']))
                    
                    # Log de acesso
                    cursor.execute("""
                        INSERT INTO memory_access_log (memory_id, user_id, context)
                        VALUES (?, ?, ?)
                    """, (memory['id'], user_id, f"recall: {key if key else 'search'}"))
                
                conn.commit()
                
                return {
                    "status": "success",
                    "operation": "recall",
                    "user_id": user_id,
                    "count": len(memories),
                    "memories": memories
                }
                
        except Exception as e:
            return {
                "status": "error",
                "operation": "recall",
                "error": str(e)
            }
    
    # ============================================================
    # TOOL 3: memory_delete - Deletar memória
    # ============================================================
    
    async def memory_delete(self, 
                           user_id: str, 
                           key: str = None,
                           category: str = None,
                           memory_id: int = None,
                           delete_all: bool = False) -> Dict:
        """
        Deleta memórias do banco HGR
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if delete_all:
                    cursor.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
                    deleted = cursor.rowcount
                    message = f"Todas as {deleted} memórias do usuário {user_id} foram deletadas"
                
                elif memory_id:
                    cursor.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
                    deleted = cursor.rowcount
                    message = f"Memória ID {memory_id} deletada" if deleted else "Memória não encontrada"
                
                elif key:
                    cursor.execute("DELETE FROM memories WHERE user_id = ? AND key = ?", (user_id, key))
                    deleted = cursor.rowcount
                    message = f"Memória '{key}' deletada" if deleted else "Chave não encontrada"
                
                elif category:
                    cursor.execute("DELETE FROM memories WHERE user_id = ? AND category = ?", (user_id, category))
                    deleted = cursor.rowcount
                    message = f"{deleted} memórias da categoria '{category}' deletadas"
                
                else:
                    return {
                        "status": "error",
                        "operation": "delete",
                        "error": "Especifique o que deletar (key, category, memory_id ou delete_all)"
                    }
                
                conn.commit()
                
                return {
                    "status": "success",
                    "operation": "delete",
                    "user_id": user_id,
                    "deleted_count": deleted,
                    "message": message
                }
                
        except Exception as e:
            return {
                "status": "error",
                "operation": "delete",
                "error": str(e)
            }
    
    # ============================================================
    # TOOL 4: memory_update - Atualizar memória existente
    # ============================================================
    
    async def memory_update(self,
                           user_id: str,
                           key: str,
                           value: Any = None,
                           importance: float = None,
                           category: str = None,
                           tags: List[str] = None,
                           increment_access: bool = True) -> Dict:
        """
        Atualiza campos específicos de uma memória
        """
        try:
            updates = []
            params = []
            
            if value is not None:
                if not isinstance(value, str):
                    value = json.dumps(value, ensure_ascii=False)
                updates.append("value = ?")
                params.append(value)
            
            if importance is not None:
                updates.append("importance = ?")
                params.append(importance)
            
            if category is not None:
                updates.append("category = ?")
                params.append(category)
            
            if tags is not None:
                updates.append("tags = ?")
                params.append(json.dumps(tags))
            
            if increment_access:
                updates.append("access_count = access_count + 1")
            
            updates.append("last_accessed = ?")
            params.append(datetime.now().isoformat())
            
            if not updates:
                return {
                    "status": "error",
                    "operation": "update",
                    "error": "Nenhum campo para atualizar"
                }
            
            params.extend([user_id, key])
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = f"""
                    UPDATE memories 
                    SET {', '.join(updates)}
                    WHERE user_id = ? AND key = ?
                """
                
                cursor.execute(query, params)
                updated = cursor.rowcount
                conn.commit()
                
                return {
                    "status": "success",
                    "operation": "update",
                    "user_id": user_id,
                    "key": key,
                    "updated": bool(updated),
                    "fields_updated": len(updates) - (2 if increment_access else 1)
                }
                
        except Exception as e:
            return {
                "status": "error",
                "operation": "update",
                "error": str(e)
            }
    
    # ============================================================
    # TOOL 5: memory_stats - Estatísticas da memória
    # ============================================================
    
    async def memory_stats(self, user_id: str = None) -> Dict:
        """
        Retorna estatísticas do sistema de memória
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if user_id:
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total,
                            AVG(importance) as avg_importance,
                            SUM(access_count) as total_accesses,
                            COUNT(DISTINCT category) as categories,
                            MAX(importance) as max_importance,
                            MIN(importance) as min_importance
                        FROM memories 
                        WHERE user_id = ?
                    """, (user_id,))
                    
                    row = cursor.fetchone()
                    
                    cursor.execute("""
                        SELECT key, importance, access_count 
                        FROM memories 
                        WHERE user_id = ? 
                        ORDER BY importance DESC 
                        LIMIT 5
                    """, (user_id,))
                    top_memories = [{"key": r[0], "importance": r[1], "accesses": r[2]} for r in cursor.fetchall()]
                    
                    cursor.execute("""
                        SELECT category, COUNT(*) 
                        FROM memories 
                        WHERE user_id = ? 
                        GROUP BY category
                    """, (user_id,))
                    categories = dict(cursor.fetchall())
                    
                    return {
                        "status": "success",
                        "operation": "stats",
                        "user_id": user_id,
                        "stats": {
                            "total_memories": row[0] if row else 0,
                            "avg_importance": round(row[1], 2) if row and row[1] else 0,
                            "total_accesses": row[2] if row else 0,
                            "unique_categories": row[3] if row else 0,
                            "importance_range": {
                                "max": row[4] if row else 0,
                                "min": row[5] if row else 0
                            },
                            "top_memories": top_memories,
                            "categories": categories
                        }
                    }
                    
                else:
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_memories,
                            COUNT(DISTINCT user_id) as total_users,
                            AVG(importance) as global_avg_importance,
                            SUM(access_count) as global_accesses
                        FROM memories
                    """)
                    
                    row = cursor.fetchone()
                    
                    cursor.execute("""
                        SELECT user_id, COUNT(*) as count 
                        FROM memories 
                        GROUP BY user_id 
                        ORDER BY count DESC 
                        LIMIT 5
                    """)
                    top_users = [{"user": r[0], "memories": r[1]} for r in cursor.fetchall()]
                    
                    return {
                        "status": "success",
                        "operation": "stats",
                        "global": True,
                        "stats": {
                            "total_memories": row[0] if row else 0,
                            "total_users": row[1] if row else 0,
                            "global_avg_importance": round(row[2], 2) if row and row[2] else 0,
                            "global_accesses": row[3] if row else 0,
                            "most_active_users": top_users
                        }
                    }
                    
        except Exception as e:
            return {
                "status": "error",
                "operation": "stats",
                "error": str(e)
            }
    
    # ============================================================
    # TOOL 6: memory_search - Busca semântica
    # ============================================================
    
    async def memory_search(self, 
                           user_id: str,
                           search_term: str,
                           in_values: bool = True,
                           in_keys: bool = True,
                           min_importance: float = 0.0) -> Dict:
        """
        Busca texto nas memórias
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                conditions = []
                params = [user_id, f"%{search_term}%"]
                
                if in_keys:
                    conditions.append("key LIKE ?")
                
                if in_values:
                    conditions.append("value LIKE ?")
                    params.append(f"%{search_term}%")
                
                if not conditions:
                    return {
                        "status": "error",
                        "operation": "search",
                        "error": "Especifique onde buscar (in_keys/in_values)"
                    }
                
                query = f"""
                    SELECT * FROM memories 
                    WHERE user_id = ? 
                    AND ({' OR '.join(conditions)})
                    AND importance >= ?
                    ORDER BY importance DESC, last_accessed DESC
                """
                params.append(min_importance)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                results = []
                for row in rows:
                    memory = dict(row)
                    if memory['tags']:
                        memory['tags'] = json.loads(memory['tags'])
                    try:
                        memory['value'] = json.loads(memory['value'])
                    except:
                        pass
                    results.append(memory)
                
                return {
                    "status": "success",
                    "operation": "search",
                    "user_id": user_id,
                    "search_term": search_term,
                    "count": len(results),
                    "results": results
                }
                
        except Exception as e:
            return {
                "status": "error",
                "operation": "search",
                "error": str(e)
            }
    
    # ============================================================
    # TOOL 7: memory_cleanup - Limpeza automática
    # ============================================================
    
    async def memory_cleanup(self, 
                            user_id: str = None,
                            older_than_days: int = 30,
                            importance_threshold: float = 0.2,
                            dry_run: bool = False) -> Dict:
        """
        Limpa memórias antigas e de baixa importância
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = """
                    SELECT id, user_id, key, importance, last_accessed
                    FROM memories 
                    WHERE last_accessed < datetime('now', ?)
                    AND importance < ?
                """
                params = [f'-{older_than_days} days', importance_threshold]
                
                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)
                
                cursor.execute(query, params)
                to_delete = cursor.fetchall()
                
                if dry_run:
                    return {
                        "status": "success",
                        "operation": "cleanup",
                        "dry_run": True,
                        "would_delete": len(to_delete),
                        "memories": [
                            {
                                "id": r[0],
                                "user_id": r[1],
                                "key": r[2],
                                "importance": r[3],
                                "last_accessed": r[4]
                            }
                            for r in to_delete
                        ]
                    }
                
                deleted_ids = [r[0] for r in to_delete]
                if deleted_ids:
                    cursor.execute(f"""
                        DELETE FROM memories 
                        WHERE id IN ({','.join(['?'] * len(deleted_ids))})
                    """, deleted_ids)
                    
                    cursor.execute(f"""
                        DELETE FROM memory_access_log 
                        WHERE memory_id IN ({','.join(['?'] * len(deleted_ids))})
                    """, deleted_ids)
                    
                    conn.commit()
                
                return {
                    "status": "success",
                    "operation": "cleanup",
                    "dry_run": False,
                    "deleted_count": len(to_delete),
                    "older_than_days": older_than_days,
                    "importance_threshold": importance_threshold
                }
                
        except Exception as e:
            return {
                "status": "error",
                "operation": "cleanup",
                "error": str(e)
            }
    
    # ============================================================
    # TOOL 8: memory_export - Exportar memórias
    # ============================================================
    
    async def memory_export(self, 
                           user_id: str,
                           format: str = "json",
                           include_stats: bool = True) -> Dict:
        """
        Exporta memórias do usuário
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM memories 
                    WHERE user_id = ? 
                    ORDER BY importance DESC
                """, (user_id,))
                
                rows = cursor.fetchall()
                memories = []
                
                for row in rows:
                    memory = dict(row)
                    if memory['tags']:
                        memory['tags'] = json.loads(memory['tags'])
                    try:
                        memory['value'] = json.loads(memory['value'])
                    except:
                        pass
                    
                    cursor.execute("""
                        SELECT accessed_at, context 
                        FROM memory_access_log 
                        WHERE memory_id = ?
                        ORDER BY accessed_at DESC
                        LIMIT 10
                    """, (memory['id'],))
                    
                    memory['recent_accesses'] = [
                        {"accessed_at": r[0], "context": r[1]}
                        for r in cursor.fetchall()
                    ]
                    
                    memories.append(memory)
                
                export_data = {
                    "user_id": user_id,
                    "exported_at": datetime.now().isoformat(),
                    "total_memories": len(memories),
                    "memories": memories
                }
                
                if include_stats:
                    cursor.execute("""
                        SELECT 
                            AVG(importance) as avg_importance,
                            SUM(access_count) as total_accesses,
                            COUNT(DISTINCT category) as unique_categories
                        FROM memories 
                        WHERE user_id = ?
                    """, (user_id,))
                    
                    stats = cursor.fetchone()
                    export_data["stats"] = {
                        "avg_importance": round(stats[0], 2) if stats[0] else 0,
                        "total_accesses": stats[1] if stats[1] else 0,
                        "unique_categories": stats[2] if stats[2] else 0
                    }
                
                filename = f"memory_export_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                filepath = os.path.join(BASE_DIR, "exports", filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                
                return {
                    "status": "success",
                    "operation": "export",
                    "user_id": user_id,
                    "format": format,
                    "count": len(memories),
                    "file": filepath,
                    "data": export_data if format == "json" else None
                }
                
        except Exception as e:
            return {
                "status": "error",
                "operation": "export",
                "error": str(e)
            }

# Instância global do MemorySQL
memory_sql = MemorySQL()

# ============================================================
# TOOL SYSTEM - 40 FERRAMENTAS (32 + 8 Memória)
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
    MEMORY = "memory"  # Nova categoria

@dataclass
class Tool:
    name: str
    description: str
    category: ToolCategory
    function: Callable
    requires_sudo: bool = False
    timeout: int = 90
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
        """Registra todas as 40 ferramentas"""
        
        # ===== PYTHON TOOLS (1-5) =====
        
        async def execute_python(code: str) -> str:
            """Executa código Python arbitrário"""
            try:
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
                        'open': None
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
                return json.dumps(processes[:20])
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
            """Download de arquivo via HTTP - salva em BASE_DIR"""
            try:
                if not filename:
                    filename = url.split('/')[-1] or 'downloaded_file'
                
                filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
                filepath = os.path.join(BASE_DIR, filename)
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=TOOL_TIMEOUT) as resp:
                        content = await resp.read()
                        with open(filepath, 'wb') as f:
                            f.write(content)
                        return f"Downloaded {len(content)} bytes to {filepath}"
            except Exception as e:
                return f"Erro download: {str(e)}"
        
        self.register(Tool(
            name="http_download",
            description="Download de arquivos via HTTP (salva em BASE_DIR)",
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
                
                for port in port_list[:10]:
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
        
        def is_path_allowed(path: str) -> bool:
            abs_path = os.path.abspath(path)
            return abs_path.startswith(BASE_DIR)
        
        async def file_read(path: str) -> str:
            """Lê conteúdo de arquivo (apenas dentro de BASE_DIR)"""
            try:
                if not is_path_allowed(path):
                    return f"Acesso negado: apenas dentro de {BASE_DIR} é permitido"
                
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return content[:2000]
            except Exception as e:
                return f"Erro leitura: {str(e)}"
        
        self.register(Tool(
            name="file_read",
            description=f"Lê arquivo (apenas dentro de {BASE_DIR})",
            category=ToolCategory.FILESYSTEM,
            function=file_read
        ))
        
        async def file_write(path: str, content: str) -> str:
            """Escreve conteúdo em arquivo (apenas dentro de BASE_DIR)"""
            try:
                if not is_path_allowed(path):
                    return f"Acesso negado: apenas dentro de {BASE_DIR} é permitido"
                
                os.makedirs(os.path.dirname(path), exist_ok=True)
                
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return f"Arquivo {path} escrito com sucesso"
            except Exception as e:
                return f"Erro escrita: {str(e)}"
        
        self.register(Tool(
            name="file_write",
            description=f"Escreve em arquivo (apenas dentro de {BASE_DIR})",
            category=ToolCategory.FILESYSTEM,
            function=file_write
        ))
        
        async def file_list(path: str = None) -> str:
            """Lista arquivos em diretório (padrão: BASE_DIR)"""
            try:
                if path is None:
                    path = BASE_DIR
                
                if not is_path_allowed(path):
                    return f"Acesso negado: apenas dentro de {BASE_DIR} é permitido"
                
                files = os.listdir(path)
                return json.dumps(files[:50])
            except Exception as e:
                return f"Erro listagem: {str(e)}"
        
        self.register(Tool(
            name="file_list",
            description=f"Lista arquivos em diretório (padrão: {BASE_DIR})",
            category=ToolCategory.FILESYSTEM,
            function=file_list
        ))
        
        async def file_delete(path: str) -> str:
            """Deleta arquivo (apenas dentro de BASE_DIR)"""
            try:
                if not is_path_allowed(path):
                    return f"Acesso negado: apenas dentro de {BASE_DIR} é permitido"
                
                os.remove(path)
                return f"Arquivo {path} deletado"
            except Exception as e:
                return f"Erro deleção: {str(e)}"
        
        self.register(Tool(
            name="file_delete",
            description=f"Deleta arquivo (apenas dentro de {BASE_DIR})",
            category=ToolCategory.FILESYSTEM,
            function=file_delete,
            dangerous=True
        ))
        
        async def file_info(path: str) -> str:
            """Informações detalhadas de arquivo"""
            try:
                if not is_path_allowed(path):
                    return f"Acesso negado: apenas dentro de {BASE_DIR} é permitido"
                
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
            """Executa query SQLite em banco (apenas dentro de BASE_DIR)"""
            try:
                if not db_path.startswith(BASE_DIR):
                    return f"Acesso negado: apenas dentro de {BASE_DIR} é permitido"
                
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
            description=f"Executa query SQLite em banco (apenas dentro de {BASE_DIR})",
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
        
        # ===== MEMORY TOOLS (33-40) =====
        
        async def memory_store(user_id: str, key: str, value: Any, 
                               importance: float = 0.5, category: str = "general",
                               tags: List[str] = None, expiry_days: int = None) -> str:
            """Armazena uma memória persistente"""
            result = await memory_sql.memory_store(
                user_id, key, value, importance, category, tags, expiry_days
            )
            return json.dumps(result, ensure_ascii=False)
        
        self.register(Tool(
            name="memory_store",
            description="Armazena uma memória persistente. Args: user_id, key, value, [importance=0.5], [category=general], [tags], [expiry_days]",
            category=ToolCategory.MEMORY,
            function=memory_store
        ))
        
        async def memory_recall(user_id: str, key: str = None, category: str = None,
                                tags: List[str] = None, min_importance: float = 0.0,
                                limit: int = 10, include_expired: bool = False) -> str:
            """Recupera memórias do banco HGR"""
            result = await memory_sql.memory_recall(
                user_id, key, category, tags, min_importance, limit, include_expired
            )
            return json.dumps(result, ensure_ascii=False)
        
        self.register(Tool(
            name="memory_recall",
            description="Recupera memórias. Args: user_id, [key], [category], [tags], [min_importance=0.0], [limit=10], [include_expired=false]",
            category=ToolCategory.MEMORY,
            function=memory_recall
        ))
        
        async def memory_delete(user_id: str, key: str = None, category: str = None,
                                memory_id: int = None, delete_all: bool = False) -> str:
            """Deleta memórias do banco HGR"""
            result = await memory_sql.memory_delete(
                user_id, key, category, memory_id, delete_all
            )
            return json.dumps(result, ensure_ascii=False)
        
        self.register(Tool(
            name="memory_delete",
            description="Deleta memórias. Args: user_id, [key], [category], [memory_id], [delete_all=false] - CUIDADO!",
            category=ToolCategory.MEMORY,
            function=memory_delete,
            dangerous=True
        ))
        
        async def memory_update(user_id: str, key: str, value: Any = None,
                                importance: float = None, category: str = None,
                                tags: List[str] = None) -> str:
            """Atualiza campos específicos de uma memória"""
            result = await memory_sql.memory_update(
                user_id, key, value, importance, category, tags
            )
            return json.dumps(result, ensure_ascii=False)
        
        self.register(Tool(
            name="memory_update",
            description="Atualiza memória existente. Args: user_id, key, [value], [importance], [category], [tags]",
            category=ToolCategory.MEMORY,
            function=memory_update
        ))
        
        async def memory_stats(user_id: str = None) -> str:
            """Retorna estatísticas do sistema de memória"""
            result = await memory_sql.memory_stats(user_id)
            return json.dumps(result, ensure_ascii=False)
        
        self.register(Tool(
            name="memory_stats",
            description="Estatísticas da memória. Args: [user_id] - se omitido, estatísticas globais",
            category=ToolCategory.MEMORY,
            function=memory_stats
        ))
        
        async def memory_search(user_id: str, search_term: str,
                                in_values: bool = True, in_keys: bool = True,
                                min_importance: float = 0.0) -> str:
            """Busca texto nas memórias"""
            result = await memory_sql.memory_search(
                user_id, search_term, in_values, in_keys, min_importance
            )
            return json.dumps(result, ensure_ascii=False)
        
        self.register(Tool(
            name="memory_search",
            description="Busca texto nas memórias. Args: user_id, search_term, [in_values=true], [in_keys=true], [min_importance=0.0]",
            category=ToolCategory.MEMORY,
            function=memory_search
        ))
        
        async def memory_cleanup(user_id: str = None, older_than_days: int = 30,
                                  importance_threshold: float = 0.2,
                                  dry_run: bool = False) -> str:
            """Limpa memórias antigas e de baixa importância"""
            result = await memory_sql.memory_cleanup(
                user_id, older_than_days, importance_threshold, dry_run
            )
            return json.dumps(result, ensure_ascii=False)
        
        self.register(Tool(
            name="memory_cleanup",
            description="Limpa memórias antigas. Args: [user_id], [older_than_days=30], [importance_threshold=0.2], [dry_run=false]",
            category=ToolCategory.MEMORY,
            function=memory_cleanup,
            dangerous=True
        ))
        
        async def memory_export(user_id: str, format: str = "json",
                                include_stats: bool = True) -> str:
            """Exporta memórias do usuário"""
            result = await memory_sql.memory_export(
                user_id, format, include_stats
            )
            return json.dumps(result, ensure_ascii=False)
        
        self.register(Tool(
            name="memory_export",
            description="Exporta memórias. Args: user_id, [format=json], [include_stats=true]",
            category=ToolCategory.MEMORY,
            function=memory_export
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
            if asyncio.iscoroutinefunction(tool.function):
                result = await tool.function(*args, **kwargs)
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    thread_pool,
                    tool.function,
                    *args, **kwargs
                )
            
            if not tool.dangerous:
                self.cache[cache_key] = result
                self.cache_ttl[cache_key] = datetime.now() + timedelta(minutes=5)
            
            if user_id not in self.execution_history:
                self.execution_history[user_id] = []
            
            self.execution_history[user_id].append({
                "tool": tool_name,
                "args": args,
                "kwargs": kwargs,
                "time": time.time() - start_time,
                "timestamp": datetime.now().isoformat()
            })
            
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

SYSTEM_PROMPT = """Você é o OPENBOT v3.0, um assistente avançado com 40 ferramentas disponíveis (32 base + 8 de memória).

CAPACIDADES PRINCIPAIS:
- Raciocínio estruturado e execução de tarefas complexas
- Uso de ferramentas para Python, Shell, Network, Filesystem
- Memória persistente de 3 níveis (curto/longo prazo + relevância)
- Execução segura em ambiente isolado
- Diretório base de trabalho: {base_dir}

FERRAMENTAS DISPONÍVEIS:
{tools_description}

MEMÓRIA PERSISTENTE:
Você tem acesso a 8 ferramentas dedicadas de memória:
- memory_store: Armazena informações importantes
- memory_recall: Recupera memórias salvas
- memory_search: Busca texto nas memórias
- memory_update: Atualiza memórias existentes
- memory_delete: Remove memórias
- memory_stats: Estatísticas da memória
- memory_cleanup: Limpa memórias antigas
- memory_export: Exporta memórias

Use estas ferramentas para lembrar informações entre conversas e personalizar respostas.

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
    
    tools_description = "\n".join([
        f"- {t['name']}: {t['description']} (Categoria: {t['category']})"
        for t in tool_registry.list_tools()
    ])
    
    enhanced_prompt = memory_agent.get_enhanced_system_prompt(
        user_id, 
        user_query, 
        SYSTEM_PROMPT.format(tools_description=tools_description, base_dir=BASE_DIR)
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
        
        tool_match = re.search(r'<tool>(.*?)</tool>', response_text, re.DOTALL)
        
        if tool_match:
            try:
                tool_call = json.loads(tool_match.group(1).strip())
                tool_name = tool_call.get("name")
                args = tool_call.get("args", [])
                kwargs = tool_call.get("kwargs", {})
                
                tool_result = await tool_engine.execute(
                    tool_name, 
                    user_id,
                    *args, 
                    **kwargs
                )
                
                tool_counter += 1
                
                messages.append({"role": "assistant", "content": response_text})
                messages.append({
                    "role": "system", 
                    "content": f"Resultado da ferramenta {tool_name}: {json.dumps(tool_result, ensure_ascii=False)}"
                })
                
                memory_agent.record_step(user_id, user_query, {
                    "step": step,
                    "thought": response_text[:100],
                    "tool": tool_name,
                    "result": tool_result
                })
                
                continue
                
            except json.JSONDecodeError as e:
                error_msg = f"Erro ao parsear chamada de ferramenta: {e}"
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "system", "content": error_msg})
                continue
        
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
        "architecture": "Plug & Play com Tool Use + Memória Persistente",
        "base_dir": BASE_DIR,
        "layers": {
            "auth": "JWT Authentication",
            "agent": "Tool-based Reasoning (40 ferramentas)",
            "memory": "HGR 3 Níveis + MemorySQL 8 Tools"
        },
        "model": MODEL,
        "resources": {
            "cpu": f"{cpu}%",
            "memory": f"{mem}MB"
        },
        "tools": {
            "total": len(tool_registry.list_tools()),
            "categories": [c.value for c in ToolCategory],
            "list": tool_registry.list_tools()[:10]
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
                "POST /api/tools/execute/{name}",
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
        "history": history[-50:]
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
    
    # Estatísticas de memória persistente
    memory_stats = await memory_sql.memory_stats(user_data['username'])
    
    return jsonify({
        "status": "success",
        "user": {
            "user_id": user_data['user_id'],
            "username": user_data['username'],
            "email": user_data['email'],
            "is_admin": user_data.get('is_admin', False)
        },
        "memory_stats": stats,
        "tool_stats": tool_stats,
        "persistent_memory": memory_stats.get('stats', {}) if memory_stats['status'] == 'success' else {}
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
    
    cpu, mem = get_resource_usage()
    
    db_sizes = {}
    for db in ["users.db", "agent_memory_v3.db", "openbot_v3.log"]:
        try:
            full_path = os.path.join(BASE_DIR, db)
            size = os.path.getsize(full_path) / (1024 * 1024)
            db_sizes[db] = f"{size:.2f} MB"
        except:
            db_sizes[db] = "N/A"
    
    all_executions = []
    for user, history in tool_engine.execution_history.items():
        all_executions.extend(history)
    
    tool_usage = {}
    for exec in all_executions:
        tool = exec['tool']
        tool_usage[tool] = tool_usage.get(tool, 0) + 1
    
    # Estatísticas de memória global
    memory_global = await memory_sql.memory_stats()
    
    return jsonify({
        "status": "success",
        "system": {
            "model": MODEL,
            "base_dir": BASE_DIR,
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
        },
        "memory": memory_global.get('stats', {}) if memory_global['status'] == 'success' else {}
    })

# ============================================================
# MAINTENANCE TASKS
# ============================================================

async def cleanup_task():
    """Limpeza periódica"""
    while True:
        await asyncio.sleep(3600)
        
        try:
            deleted = cleanup_old_tokens(user_db, days=7)
            if deleted > 0:
                logging.info(f"Tokens removidos: {deleted}")
            
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
            
            # Limpeza automática de memórias antigas (dry_run=True para não deletar)
            cleanup_result = await memory_sql.memory_cleanup(
                older_than_days=30,
                importance_threshold=0.1,
                dry_run=True
            )
            if cleanup_result['status'] == 'success' and cleanup_result.get('would_delete', 0) > 0:
                logging.info(f"Memórias candidatas a limpeza: {cleanup_result['would_delete']}")
            
        except Exception as e:
            logging.error(f"Erro na limpeza: {e}")

@app.before_serving
async def startup():
    """Inicialização"""
    asyncio.create_task(cleanup_task())
    
    try:
        test = await async_llm([{"role": "user", "content": "teste"}])
        print(f"✅ GROQ conectado: {test[:50]}...")
    except Exception as e:
        print(f"⚠️ GROQ: {e}")
    
    print("\n" + "="*70)
    print("🚀 OPENBOT v3.0 - ARQUITETURA PLUG & PLAY COM TOOL USE")
    print("="*70)
    print(f"📂 DIRETÓRIO BASE: {BASE_DIR}")
    print("="*70)
    print("📦 CAMADA DE FERRAMENTAS (40):")
    print("   • Python     (5)  • Shell    (5)  • Network  (6)")
    print("   • Filesystem (5)  • Data     (4)  • System   (3)")
    print("   • Crypto     (2)  • Utility  (4)  • Memory   (8)")
    print("-"*70)
    print("🔧 CORE API:")
    print("   • AUTH    - JWT Authentication")
    print("   • AGENT   - Tool-based Reasoning")
    print("   • MEMORY  - HGR 3 Níveis + MemorySQL")
    print("   • CACHE   - Tool Result Caching")
    print("-"*70)
    print("💾 DATABASES (dentro do diretório base):")
    print("   • users.db            - Dados dos usuários")
    print("   • agent_memory_v3.db  - Memória persistente (HGR + MemorySQL)")
    print("   • openbot_v3.log      - Logs do sistema")
    print("   • exports/            - Exports de memória")
    print("-"*70)
    print("⚡ Plug & Play com Tool Use + Memória Persistente:")
    print("   • 40 ferramentas integradas (32 base + 8 memória)")
    print("   • Cache inteligente (5 min TTL)")
    print("   • Execução segura em sandbox")
    print("   • Histórico por usuário")
    print("   • Memória persistente com 8 operações")
    print("   • Streaming em tempo real")
    print("="*70)
    print(f"🌐 http://0.0.0.0:5000")
    print(f"🔧 Total de ferramentas: {len(tool_registry.list_tools())}")
    print("="*70)
    
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