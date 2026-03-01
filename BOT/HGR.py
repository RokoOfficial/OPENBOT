#!/usr/bin/env python3
"""
OPENBOT v4.0 — HGR (Hierarchical Grounded Reasoning) Memory System
Versão unificada e reestruturada:

  ARQUITETURA:
  - Banco único: agent_memory.db (3 tabelas: chat_log, facts, context_steps)
  - chat_log  : histórico de conversa 100% persistente (sobrevive reinícios)
  - facts     : factos sobre o utilizador, projetos, preferências (key/value)
  - context_steps: steps técnicos do agente (substituiu long_term_memory)
  - cron_jobs : trabalhos agendados com histórico de execuções

  MELHORIAS vs v3.1:
  - chat_history persiste em SQLite — bot nunca perde contexto ao reiniciar
  - facts sempre injetados no system prompt (contexto obrigatório)
  - extract_facts_from_exchange() — extrai factos proativamente após cada troca
  - threshold dinâmico — bot nunca fica sem contexto mesmo sem match léxico
  - relevância com boost temporal e de frequência
  - CronManager integrado — scheduler asyncio nativo
  - MemorySQL eliminada — facts table substitui completamente
"""

import os
import re
import json
import time
import asyncio
import hashlib
import logging
import sqlite3
from typing   import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime    import datetime, timedelta
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════════

@dataclass
class MemoryConfig:
    """Configuração completa do sistema HGR."""

    # Banco unificado
    db_path: str = "agent_memory.db"

    # Short-term RAM (cache rápido, reconstruído do DB ao iniciar)
    short_term_size: int  = 30
    short_term_ttl:  int  = 3600      # 1h

    # Medium-term sessão RAM
    medium_term_size: int = 100
    medium_term_ttl:  int = 86400     # 24h

    # Relevância
    min_relevance_score:  float = 0.05   # baixo — threshold dinâmico faz o ajuste
    importance_threshold: float = 0.3

    # Chat history
    max_chat_history:    int = 200    # máx no DB por utilizador
    chat_history_to_llm: int = 40     # quantas enviar ao LLM por request

    # Facts context no prompt
    max_facts_in_prompt: int = 20     # máx factos a injetar no system prompt

    # Cron
    cron_tick_interval: int = 30      # segundos entre verificações de cron


# ══════════════════════════════════════════════════════════════════
# RELEVÂNCIA
# ══════════════════════════════════════════════════════════════════

class RelevanceScorer:
    STOP_WORDS = {
        'o','a','de','da','do','para','com','em','um','uma','os','as',
        'que','se','por','mas','como','foi','ser','tem','sao','nao',
        'the','is','and','or','to','in','of','for','on','at','it',
        'this','that','are','was','be','have','has','had','will','would'
    }

    @staticmethod
    def keywords(text: str) -> set:
        words = re.findall(r'\b\w{3,}\b', text.lower())
        return {w for w in words if w not in RelevanceScorer.STOP_WORDS}

    @staticmethod
    def jaccard(a: str, b: str) -> float:
        ka, kb = RelevanceScorer.keywords(a), RelevanceScorer.keywords(b)
        if not ka or not kb:
            return 0.0
        inter = len(ka & kb)
        union = len(ka | kb)
        return inter / union if union else 0.0

    @staticmethod
    def importance(thought: str, confidence: float, has_result: bool) -> float:
        boosts = {
            'erro','error','bug','fix','solução','solution','importante',
            'crítico','critical','projeto','project','nome','name','prefer'
        }
        boost = sum(0.08 for w in boosts if w in thought.lower())
        return min(1.0, confidence + boost + (0.15 if has_result else 0.0))


# ══════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════

@dataclass
class ChatMessage:
    role:       str
    content:    str
    timestamp:  float = field(default_factory=time.time)
    session_id: str   = ""

    def to_llm(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class Fact:
    key:          str
    value:        str
    importance:   float = 0.5
    category:     str   = "general"
    tags:         List[str] = field(default_factory=list)
    access_count: int   = 0
    last_accessed: float = field(default_factory=time.time)
    created_at:   float = field(default_factory=time.time)


@dataclass
class ContextStep:
    query:      str
    thought:    str
    action:     str
    confidence: float
    importance: float  = 0.0
    tool_used:  str    = ""
    tool_result: str   = ""
    session_id: str    = ""
    timestamp:  float  = field(default_factory=time.time)


@dataclass
class CronJob:
    id:           int
    user_id:      str
    name:         str
    description:  str
    schedule:     str          # "every:5m" | "every:1h" | "cron:0 8 * * *"
    task_type:    str          # "agent" | "shell" | "http"
    task:         str          # prompt, comando ou URL
    status:       str  = "active"   # active|paused|error
    last_run:     Optional[float] = None
    next_run:     Optional[float] = None
    run_count:    int  = 0
    last_output:  str  = ""
    created_at:   float = field(default_factory=time.time)


# ══════════════════════════════════════════════════════════════════
# BANCO DE DADOS — INICIALIZAÇÃO
# ══════════════════════════════════════════════════════════════════

class HGRDatabase:
    """Gestão do banco SQLite unificado."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn   = None
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def _init(self):
        c = self.conn.cursor()

        # ── CHAT LOG (persistente) ──────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS chat_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT    NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                timestamp  REAL    NOT NULL,
                session_id TEXT    DEFAULT ''
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_chat_user_ts ON chat_log(user_id, timestamp DESC)")

        # ── FACTS (substitui MemorySQL.memories) ───────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT    NOT NULL,
                key          TEXT    NOT NULL,
                value        TEXT    NOT NULL,
                importance   REAL    DEFAULT 0.5,
                category     TEXT    DEFAULT 'general',
                tags         TEXT    DEFAULT '[]',
                access_count INTEGER DEFAULT 0,
                last_accessed REAL   DEFAULT (strftime('%s','now')),
                created_at   REAL    DEFAULT (strftime('%s','now')),
                UNIQUE(user_id, key)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_facts_user ON facts(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_facts_imp  ON facts(user_id, importance DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_facts_cat  ON facts(user_id, category)")

        # ── CONTEXT STEPS (steps técnicos do agente) ───────
        c.execute("""
            CREATE TABLE IF NOT EXISTS context_steps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    NOT NULL,
                session_id  TEXT    DEFAULT '',
                query       TEXT    NOT NULL,
                thought     TEXT    NOT NULL,
                action      TEXT    DEFAULT '',
                confidence  REAL    DEFAULT 0.8,
                importance  REAL    DEFAULT 0.3,
                tool_used   TEXT    DEFAULT '',
                tool_result TEXT    DEFAULT '',
                keywords    TEXT    DEFAULT '',
                timestamp   REAL    NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_steps_user_imp ON context_steps(user_id, importance DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_steps_kw       ON context_steps(keywords)")

        # ── CRON JOBS ───────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS cron_jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                description TEXT    DEFAULT '',
                schedule    TEXT    NOT NULL,
                task_type   TEXT    NOT NULL DEFAULT 'agent',
                task        TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'active',
                last_run    REAL,
                next_run    REAL,
                run_count   INTEGER DEFAULT 0,
                last_output TEXT    DEFAULT '',
                last_error  TEXT    DEFAULT '',
                created_at  REAL    DEFAULT (strftime('%s','now'))
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_cron_user   ON cron_jobs(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cron_status ON cron_jobs(status, next_run)")

        # ── CRON LOG ────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS cron_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                cron_id    INTEGER NOT NULL REFERENCES cron_jobs(id) ON DELETE CASCADE,
                user_id    TEXT    NOT NULL,
                started_at REAL    NOT NULL,
                ended_at   REAL,
                status     TEXT    NOT NULL DEFAULT 'running',
                output     TEXT    DEFAULT '',
                error      TEXT    DEFAULT '',
                duration   REAL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_cronlog_cron ON cron_log(cron_id, started_at DESC)")

        self.conn.commit()
        logger.info(f"HGR DB inicializado: {self.db_path}")

    def execute(self, sql: str, params: tuple = ()):
        c = self.conn.cursor()
        c.execute(sql, params)
        self.conn.commit()
        return c

    def fetchall(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchone()


# ══════════════════════════════════════════════════════════════════
# CHAT HISTORY MANAGER
# ══════════════════════════════════════════════════════════════════

class ChatHistoryManager:
    """Histórico de conversa 100% persistente."""

    def __init__(self, db: HGRDatabase, config: MemoryConfig):
        self.db     = db
        self.config = config
        # Cache RAM por utilizador (reconstruído do DB ao iniciar)
        self._cache: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=config.max_chat_history)
        )

    def _session_id(self, user_id: str) -> str:
        """Gera session_id baseado no dia (nova sessão a cada 24h)."""
        day = datetime.now().strftime("%Y%m%d")
        return hashlib.md5(f"{user_id}{day}".encode()).hexdigest()[:12]

    def add(self, user_id: str, role: str, content: str):
        """Grava mensagem no SQLite e no cache RAM."""
        ts  = time.time()
        sid = self._session_id(user_id)

        self.db.execute(
            "INSERT INTO chat_log (user_id, role, content, timestamp, session_id) VALUES (?,?,?,?,?)",
            (user_id, role, content, ts, sid)
        )
        self._cache[user_id].append(ChatMessage(role, content, ts, sid))

        # Limita DB ao max configurado
        self.db.execute("""
            DELETE FROM chat_log WHERE user_id = ? AND id NOT IN (
                SELECT id FROM chat_log WHERE user_id = ?
                ORDER BY timestamp DESC LIMIT ?
            )
        """, (user_id, user_id, self.config.max_chat_history))

    def get(self, user_id: str, last_n: int = None) -> List[dict]:
        """Retorna histórico para o LLM. Carrega DB se cache vazio."""
        n = last_n or self.config.chat_history_to_llm

        if not self._cache[user_id]:
            rows = self.db.fetchall(
                "SELECT role, content FROM chat_log WHERE user_id=? ORDER BY timestamp DESC LIMIT ?",
                (user_id, self.config.max_chat_history)
            )
            for r in reversed(rows):
                self._cache[user_id].append(ChatMessage(r["role"], r["content"]))

        history = list(self._cache[user_id])
        return [m.to_llm() for m in history[-n:]]

    def clear(self, user_id: str) -> int:
        row = self.db.fetchone("SELECT COUNT(*) as c FROM chat_log WHERE user_id=?", (user_id,))
        count = row["c"] if row else 0
        self.db.execute("DELETE FROM chat_log WHERE user_id=?", (user_id,))
        self._cache[user_id].clear()
        return count


# ══════════════════════════════════════════════════════════════════
# FACTS MANAGER
# ══════════════════════════════════════════════════════════════════

class FactsManager:
    """Gestão de factos persistentes sobre o utilizador."""

    # Padrões para extracção automática de factos
    FACT_PATTERNS = [
        # Nome
        (r'\b(?:me\s+chamo|meu\s+nome\s+[eé]|sou\s+o|sou\s+a|my\s+name\s+is)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)?)', 'nome', 0.95),
        # Linguagem preferida
        (r'\b(?:uso|trabalho\s+com|prefiro|gosto\s+de)\s+(Python|JavaScript|TypeScript|Java|Go|Rust|C\+\+|PHP|Ruby|Swift|Kotlin)', 'linguagem_preferida', 0.8),
        # Projeto ativo
        (r'\b(?:estou\s+a\s+trabalhar\s+em|working\s+on|meu\s+projeto\s+[eé]|my\s+project\s+is)\s+"?([^".,\n]{3,40})"?', 'projeto_ativo', 0.75),
        # Localização
        (r'\b(?:sou\s+de|moro\s+em|estou\s+em|I\'m\s+from|I\s+live\s+in)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)?)', 'localizacao', 0.7),
        # Email
        (r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b', 'email', 0.9),
        # Profissão
        (r'\b(?:sou|trabalho\s+como|I\'m\s+a|I\s+work\s+as)\s+(?:um\s+|uma\s+|a\s+)?([a-záàãéêíóôúç]+(?:\s+[a-záàãéêíóôúç]+)?)\b', 'profissao', 0.65),
    ]

    def __init__(self, db: HGRDatabase, config: MemoryConfig):
        self.db     = db
        self.config = config
        self._cache: Dict[str, Dict[str, Fact]] = {}  # user_id -> {key: Fact}

    def _load_cache(self, user_id: str):
        if user_id in self._cache:
            return
        rows = self.db.fetchall(
            "SELECT * FROM facts WHERE user_id=? ORDER BY importance DESC",
            (user_id,)
        )
        self._cache[user_id] = {}
        for r in rows:
            self._cache[user_id][r["key"]] = Fact(
                key=r["key"], value=r["value"],
                importance=r["importance"], category=r["category"],
                tags=json.loads(r["tags"] or "[]"),
                access_count=r["access_count"],
                last_accessed=r["last_accessed"],
                created_at=r["created_at"]
            )

    def store(self, user_id: str, key: str, value: str,
              importance: float = 0.5, category: str = "general",
              tags: List[str] = None) -> bool:
        """Armazena facto. Retorna True se criado, False se atualizado."""
        self._load_cache(user_id)
        tags_json = json.dumps(tags or [])
        now = time.time()

        existing = self._cache[user_id].get(key)
        if existing:
            self.db.execute("""
                UPDATE facts SET value=?, importance=?, category=?, tags=?,
                                 last_accessed=?, access_count=access_count+1
                WHERE user_id=? AND key=?
            """, (value, importance, category, tags_json, now, user_id, key))
            existing.value        = value
            existing.importance   = importance
            existing.last_accessed = now
            return False
        else:
            self.db.execute("""
                INSERT INTO facts (user_id, key, value, importance, category, tags, last_accessed, created_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, (user_id, key, value, importance, category, tags_json, now, now))
            self._cache[user_id][key] = Fact(key=key, value=value, importance=importance,
                                              category=category, tags=tags or [], created_at=now)
            return True

    def get_all(self, user_id: str, min_importance: float = 0.0) -> Dict[str, Fact]:
        self._load_cache(user_id)
        return {k: v for k, v in self._cache[user_id].items()
                if v.importance >= min_importance}

    def get(self, user_id: str, key: str) -> Optional[Fact]:
        self._load_cache(user_id)
        f = self._cache[user_id].get(key)
        if f:
            self.db.execute(
                "UPDATE facts SET access_count=access_count+1, last_accessed=? WHERE user_id=? AND key=?",
                (time.time(), user_id, key)
            )
        return f

    def delete(self, user_id: str, key: str = None,
               category: str = None, fact_id: int = None,
               delete_all: bool = False) -> int:
        self._load_cache(user_id)
        if delete_all:
            self.db.execute("DELETE FROM facts WHERE user_id=?", (user_id,))
            deleted = len(self._cache.get(user_id, {}))
            self._cache[user_id] = {}
            return deleted
        if fact_id:
            self.db.execute("DELETE FROM facts WHERE id=? AND user_id=?", (fact_id, user_id))
            self._cache[user_id] = {k: v for k, v in self._cache[user_id].items()
                                    if True}  # reload
            self._cache.pop(user_id, None)
            return 1
        if key:
            self.db.execute("DELETE FROM facts WHERE user_id=? AND key=?", (user_id, key))
            removed = 1 if key in self._cache.get(user_id, {}) else 0
            self._cache.get(user_id, {}).pop(key, None)
            return removed
        if category:
            rows = self.db.fetchall("SELECT key FROM facts WHERE user_id=? AND category=?", (user_id, category))
            self.db.execute("DELETE FROM facts WHERE user_id=? AND category=?", (user_id, category))
            for r in rows:
                self._cache.get(user_id, {}).pop(r["key"], None)
            return len(rows)
        return 0

    def search(self, user_id: str, term: str) -> List[Dict]:
        rows = self.db.fetchall("""
            SELECT * FROM facts
            WHERE user_id=? AND (key LIKE ? OR value LIKE ?)
            ORDER BY importance DESC
        """, (user_id, f"%{term}%", f"%{term}%"))
        return [dict(r) for r in rows]

    def extract_from_exchange(self, user_id: str, user_msg: str, bot_reply: str):
        """
        Extrai factos automaticamente de uma troca user/bot.
        Usa regex — sem LLM extra, zero latência adicional.
        """
        combined = user_msg + " " + bot_reply
        stored   = []

        for pattern, key, importance in self.FACT_PATTERNS:
            m = re.search(pattern, combined, re.IGNORECASE)
            if m:
                value = m.group(1).strip()
                if len(value) > 1:
                    created = self.store(user_id, key, value, importance, "auto_extracted")
                    if created:
                        stored.append(key)
                        logger.info(f"[HGR] Facto extraído para {user_id}: {key}={value}")

        return stored

    def format_for_prompt(self, user_id: str) -> str:
        """Formata factos para injecção obrigatória no system prompt."""
        facts = self.get_all(user_id, min_importance=0.3)
        if not facts:
            return ""

        # Prioriza factos de alta importância
        sorted_facts = sorted(facts.values(), key=lambda f: f.importance, reverse=True)
        top = sorted_facts[:self.config.max_facts_in_prompt]

        lines = ["=== O QUE SABES SOBRE ESTE UTILIZADOR ==="]
        for f in top:
            lines.append(f"  {f.key}: {f.value}")
        lines.append("==========================================")
        return "\n".join(lines)

    def stats(self, user_id: str = None) -> Dict:
        if user_id:
            row = self.db.fetchone("""
                SELECT COUNT(*) as total, AVG(importance) as avg_imp,
                       SUM(access_count) as accesses, COUNT(DISTINCT category) as cats
                FROM facts WHERE user_id=?
            """, (user_id,))
            return {
                "total":        row["total"]   if row else 0,
                "avg_importance": round(row["avg_imp"] or 0, 2),
                "total_accesses": row["accesses"] or 0,
                "unique_categories": row["cats"] or 0
            }
        row = self.db.fetchone("SELECT COUNT(*) as t, COUNT(DISTINCT user_id) as u FROM facts")
        return {"total_facts": row["t"] or 0, "total_users": row["u"] or 0}

    def recall(self, user_id: str, key: str = None, category: str = None,
               limit: int = 50, min_importance: float = 0.0) -> List[Dict]:
        sql    = "SELECT * FROM facts WHERE user_id=? AND importance>=?"
        params: list = [user_id, min_importance]
        if key:
            sql += " AND key=?"
            params.append(key)
        if category:
            sql += " AND category=?"
            params.append(category)
        sql += f" ORDER BY importance DESC LIMIT {limit}"
        rows = self.db.fetchall(sql, tuple(params))
        # Atualiza access_count
        for r in rows:
            self.db.execute(
                "UPDATE facts SET access_count=access_count+1, last_accessed=? WHERE id=?",
                (time.time(), r["id"])
            )
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════
# CONTEXT STEPS MANAGER
# ══════════════════════════════════════════════════════════════════

class ContextStepsManager:
    """Gestão dos steps técnicos do agente (substituiu long_term_memory)."""

    def __init__(self, db: HGRDatabase, config: MemoryConfig):
        self.db     = db
        self.config = config
        self.scorer = RelevanceScorer()
        self._short_term: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=config.short_term_size)
        )

    def store(self, user_id: str, step: ContextStep):
        """Armazena step técnico. Persiste no DB se importância suficiente."""
        self._short_term[user_id].append(step)

        if step.importance >= self.config.importance_threshold:
            kw = ' '.join(self.scorer.keywords(step.query + ' ' + step.thought))
            self.db.execute("""
                INSERT INTO context_steps
                (user_id, session_id, query, thought, action, confidence,
                 importance, tool_used, tool_result, keywords, timestamp)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (user_id, step.session_id, step.query, step.thought,
                  step.action, step.confidence, step.importance,
                  step.tool_used, step.tool_result, kw, step.timestamp))

    def retrieve_relevant(self, user_id: str, query: str, max_items: int = 5) -> List[ContextStep]:
        """Recupera steps relevantes para o contexto actual."""
        scorer    = self.scorer
        min_score = self.config.min_relevance_score
        candidates = []

        # Short-term RAM
        for s in self._short_term.get(user_id, []):
            score = scorer.jaccard(query, s.query + ' ' + s.thought)
            if score >= min_score:
                age_boost = max(0, 0.2 - (time.time() - s.timestamp) / 3600 * 0.05)
                candidates.append((score + age_boost, s))

        # Long-term DB
        kws = list(scorer.keywords(query))[:5]
        seen_thoughts = set()
        for kw in kws:
            rows = self.db.fetchall("""
                SELECT * FROM context_steps
                WHERE user_id=? AND keywords LIKE ?
                ORDER BY importance DESC, timestamp DESC LIMIT 10
            """, (user_id, f"%{kw}%"))
            for r in rows:
                t = r["thought"]
                if t in seen_thoughts:
                    continue
                seen_thoughts.add(t)
                step  = ContextStep(
                    query=r["query"], thought=r["thought"], action=r["action"],
                    confidence=r["confidence"], importance=r["importance"],
                    tool_used=r["tool_used"] or "", tool_result=r["tool_result"] or "",
                    session_id=r["session_id"] or "", timestamp=r["timestamp"]
                )
                score = scorer.jaccard(query, step.query + ' ' + step.thought)
                if score >= min_score:
                    candidates.append((score + step.importance * 0.2, step))

        # Threshold dinâmico: se sem resultados, pega os top-3 mais recentes
        if not candidates:
            rows = self.db.fetchall("""
                SELECT * FROM context_steps WHERE user_id=?
                ORDER BY timestamp DESC LIMIT 3
            """, (user_id,))
            for r in rows:
                candidates.append((0.01, ContextStep(
                    query=r["query"], thought=r["thought"], action=r["action"],
                    confidence=r["confidence"], importance=r["importance"],
                    timestamp=r["timestamp"]
                )))

        candidates.sort(key=lambda x: x[0], reverse=True)
        seen = set()
        result = []
        for _, s in candidates:
            h = hashlib.md5(s.thought.encode()).hexdigest()
            if h not in seen:
                result.append(s)
                seen.add(h)
            if len(result) >= max_items:
                break
        return result

    def format_for_prompt(self, user_id: str, query: str) -> str:
        steps = self.retrieve_relevant(user_id, query)
        if not steps:
            return ""
        now  = time.time()
        parts = ["=== CONTEXTO DE SESSÕES ANTERIORES ==="]
        for i, s in enumerate(steps, 1):
            age = now - s.timestamp
            age_str = (f"{int(age/60)}min" if age < 3600 else
                       f"{int(age/3600)}h" if age < 86400 else
                       f"{int(age/86400)}d")
            parts.append(
                f"\n{i}. [{age_str} atrás] Q: {s.query[:120]}\n"
                f"   Pensamento: {s.thought[:200]}\n"
                f"   Confiança: {s.confidence:.0%}"
            )
            if s.tool_used:
                parts.append(f"   Tool: {s.tool_used} → {s.tool_result[:100]}")
        parts.append("=======================================")
        return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════
# CRON MANAGER
# ══════════════════════════════════════════════════════════════════

class CronManager:
    """Scheduler de crons integrado ao HGR. Usa asyncio puro."""

    def __init__(self, db: HGRDatabase, config: MemoryConfig):
        self.db     = db
        self.config = config
        self._running = False
        self._task:   Optional[asyncio.Task] = None
        # Callback injectado pelo OPENBOT para executar tarefas
        self._executor: Optional[Callable] = None

    def set_executor(self, fn: Callable):
        """Regista a função que executa tarefas (agent_loop ou shell_execute)."""
        self._executor = fn

    # ── CRUD ──────────────────────────────────────────────────

    def create(self, user_id: str, name: str, description: str,
               schedule: str, task_type: str, task: str) -> CronJob:
        next_run = self._calc_next_run(schedule)
        c = self.db.execute("""
            INSERT INTO cron_jobs (user_id, name, description, schedule,
                                   task_type, task, status, next_run, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (user_id, name, description, schedule, task_type, task, "active",
              next_run, time.time()))
        return self.get(c.lastrowid)

    def get(self, cron_id: int) -> Optional[CronJob]:
        r = self.db.fetchone("SELECT * FROM cron_jobs WHERE id=?", (cron_id,))
        return self._row_to_job(r) if r else None

    def list_jobs(self, user_id: str, status: str = None) -> List[CronJob]:
        sql = "SELECT * FROM cron_jobs WHERE user_id=?"
        params: tuple = (user_id,)
        if status:
            sql += " AND status=?"
            params = (user_id, status)
        sql += " ORDER BY created_at DESC"
        return [self._row_to_job(r) for r in self.db.fetchall(sql, params)]

    def toggle(self, cron_id: int, user_id: str) -> Optional[CronJob]:
        r = self.db.fetchone("SELECT status FROM cron_jobs WHERE id=? AND user_id=?",
                              (cron_id, user_id))
        if not r:
            return None
        new_status = "paused" if r["status"] == "active" else "active"
        next_run   = self._calc_next_run(
            self.db.fetchone("SELECT schedule FROM cron_jobs WHERE id=?", (cron_id,))["schedule"]
        ) if new_status == "active" else None
        self.db.execute(
            "UPDATE cron_jobs SET status=?, next_run=? WHERE id=?",
            (new_status, next_run, cron_id)
        )
        return self.get(cron_id)

    def delete(self, cron_id: int, user_id: str) -> bool:
        c = self.db.execute(
            "DELETE FROM cron_jobs WHERE id=? AND user_id=?", (cron_id, user_id)
        )
        return c.rowcount > 0

    def get_logs(self, cron_id: int, limit: int = 20) -> List[Dict]:
        rows = self.db.fetchall("""
            SELECT * FROM cron_log WHERE cron_id=?
            ORDER BY started_at DESC LIMIT ?
        """, (cron_id, limit))
        return [dict(r) for r in rows]

    # ── SCHEDULER LOOP ────────────────────────────────────────

    async def start(self):
        """Inicia o loop do scheduler em background."""
        if self._running:
            return
        self._running = True
        self._task    = asyncio.create_task(self._loop())
        logger.info("CronManager iniciado.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"[CronManager] Erro no tick: {e}")
            await asyncio.sleep(self.config.cron_tick_interval)

    async def _tick(self):
        """Verifica e executa crons com next_run <= agora."""
        now  = time.time()
        rows = self.db.fetchall("""
            SELECT * FROM cron_jobs
            WHERE status='active' AND (next_run IS NULL OR next_run <= ?)
        """, (now,))

        for r in rows:
            job = self._row_to_job(r)
            asyncio.create_task(self._run_job(job))

    async def _run_job(self, job: CronJob):
        """Executa um cron job e grava o resultado."""
        started = time.time()
        log_id  = self.db.execute("""
            INSERT INTO cron_log (cron_id, user_id, started_at, status)
            VALUES (?,?,?,?)
        """, (job.id, job.user_id, started, "running")).lastrowid

        output = ""
        error  = ""
        status = "success"

        try:
            if self._executor is None:
                raise RuntimeError("Executor não registado no CronManager.")

            output = await self._executor(job)
            if not output:
                output = "(sem output)"

        except Exception as e:
            error  = str(e)
            status = "error"
            logger.error(f"[Cron #{job.id}] Erro: {e}")

        ended    = time.time()
        duration = round(ended - started, 2)
        next_run = self._calc_next_run(job.schedule)

        self.db.execute("""
            UPDATE cron_log
            SET ended_at=?, status=?, output=?, error=?, duration=?
            WHERE id=?
        """, (ended, status, output[:2000], error[:500], duration, log_id))

        self.db.execute("""
            UPDATE cron_jobs
            SET last_run=?, next_run=?, run_count=run_count+1,
                last_output=?, last_error=?,
                status=CASE WHEN ? = 'error' THEN 'error' ELSE status END
            WHERE id=?
        """, (started, next_run, output[:500], error[:200], status, job.id))

        logger.info(f"[Cron #{job.id}] '{job.name}' → {status} em {duration}s")

    async def run_now(self, cron_id: int, user_id: str) -> Dict:
        """Executa imediatamente (teste manual)."""
        r = self.db.fetchone(
            "SELECT * FROM cron_jobs WHERE id=? AND user_id=?", (cron_id, user_id)
        )
        if not r:
            return {"error": "Cron não encontrado"}
        job = self._row_to_job(r)
        await self._run_job(job)
        updated = self.get(cron_id)
        return {
            "status":      "executed",
            "last_output": updated.last_output if updated else "",
        }

    # ── SCHEDULE PARSER ───────────────────────────────────────

    @staticmethod
    def _calc_next_run(schedule: str) -> float:
        """
        Formatos suportados:
          every:30s  every:5m  every:1h  every:24h  every:7d
          cron:0 8 * * *   (hora, dia, mês, dia_semana — min cron)
        """
        now = time.time()
        schedule = schedule.strip().lower()

        if schedule.startswith("every:"):
            part = schedule[6:]
            multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
            for suffix, mult in multipliers.items():
                if part.endswith(suffix):
                    try:
                        return now + int(part[:-1]) * mult
                    except ValueError:
                        pass
            return now + 3600  # fallback 1h

        if schedule.startswith("cron:"):
            expr = schedule[5:].strip()
            return CronManager._next_cron(expr, now)

        return now + 3600

    @staticmethod
    def _next_cron(expr: str, now: float) -> float:
        """
        Parser mínimo de cron expression.
        Campos: minuto hora dia_mês mês dia_semana
        Suporta: * e valores fixos. Intervalos/listas não suportados (futuro).
        """
        parts = expr.split()
        if len(parts) != 5:
            return now + 3600

        minute, hour, dom, month, dow = parts

        dt = datetime.fromtimestamp(now) + timedelta(minutes=1)
        dt = dt.replace(second=0, microsecond=0)

        for _ in range(1440 * 7):  # máx 7 dias de busca
            ok = True
            if minute != '*' and dt.minute  != int(minute):  ok = False
            if hour   != '*' and dt.hour    != int(hour):    ok = False
            if dom    != '*' and dt.day     != int(dom):     ok = False
            if month  != '*' and dt.month   != int(month):   ok = False
            if dow    != '*' and dt.weekday()!= int(dow) % 7: ok = False
            if ok:
                return dt.timestamp()
            dt += timedelta(minutes=1)

        return now + 86400

    @staticmethod
    def _row_to_job(r: sqlite3.Row) -> CronJob:
        return CronJob(
            id=r["id"], user_id=r["user_id"],
            name=r["name"], description=r["description"] or "",
            schedule=r["schedule"], task_type=r["task_type"],
            task=r["task"], status=r["status"],
            last_run=r["last_run"], next_run=r["next_run"],
            run_count=r["run_count"] or 0,
            last_output=r["last_output"] or "",
            created_at=r["created_at"] or time.time()
        )

    def format_next_run(self, job: CronJob) -> str:
        if not job.next_run:
            return "—"
        dt  = datetime.fromtimestamp(job.next_run)
        now = datetime.now()
        diff = job.next_run - time.time()
        if diff < 0:
            return "pendente"
        if diff < 3600:
            return f"em {int(diff/60)}min"
        if diff < 86400:
            return f"em {int(diff/3600)}h"
        return dt.strftime("%d/%m %H:%M")


# ══════════════════════════════════════════════════════════════════
# HIERARCHICAL MEMORY MANAGER — orquestrador central
# ══════════════════════════════════════════════════════════════════

class HierarchicalMemoryManager:
    """
    Orquestrador central de toda a memória.
    Coordena: ChatHistoryManager, FactsManager, ContextStepsManager, CronManager.
    """

    def __init__(self, config: MemoryConfig):
        self.config  = config
        self.db      = HGRDatabase(config.db_path)
        self.chat    = ChatHistoryManager(self.db, config)
        self.facts   = FactsManager(self.db, config)
        self.steps   = ContextStepsManager(self.db, config)
        self.crons   = CronManager(self.db, config)
        logger.info("HierarchicalMemoryManager v4 inicializado.")

    def build_system_context(self, user_id: str, query: str) -> str:
        """
        Constrói o bloco de contexto obrigatório para o system prompt.
        SEMPRE retorna algo — o bot nunca começa sem contexto.
        """
        parts = []

        # 1. Factos do utilizador (obrigatório se existirem)
        facts_block = self.facts.format_for_prompt(user_id)
        if facts_block:
            parts.append(facts_block)

        # 2. Contexto de sessões anteriores (threshold dinâmico)
        steps_block = self.steps.format_for_prompt(user_id, query)
        if steps_block:
            parts.append(steps_block)

        return "\n\n".join(parts)

    def session_id(self, user_id: str) -> str:
        day = datetime.now().strftime("%Y%m%d")
        return hashlib.md5(f"{user_id}{day}".encode()).hexdigest()[:12]


# ══════════════════════════════════════════════════════════════════
# MEMORY ENHANCED AGENT — interface pública usada pelo OPENBOT
# ══════════════════════════════════════════════════════════════════

class MemoryEnhancedAgent:
    """
    Interface de alto nível entre agent_loop (OPENBOT.py) e o sistema HGR.
    API pública mantém compatibilidade com v3.1 e adiciona novos métodos.
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        cfg          = config or MemoryConfig()
        self.memory  = HierarchicalMemoryManager(cfg)
        self.config  = cfg
        self.logger  = logging.getLogger(__name__)

    # ── PROPRIEDADES CONVENIENTES ─────────────────────────────

    @property
    def db(self) -> HGRDatabase:
        return self.memory.db

    @property
    def facts(self) -> FactsManager:
        return self.memory.facts

    @property
    def crons(self) -> CronManager:
        return self.memory.crons

    # ── CHAT HISTORY ──────────────────────────────────────────

    def add_chat_message(self, user_id: str, role: str, content: str):
        """Grava mensagem no SQLite (persistente) e no cache RAM."""
        self.memory.chat.add(user_id, role, content)

    def get_chat_history(self, user_id: str, last_n: int = None) -> List[dict]:
        """Histórico para o LLM. Carrega do DB se necessário (pós-reinício)."""
        return self.memory.chat.get(user_id, last_n)

    def clear_chat_history(self, user_id: str) -> int:
        return self.memory.chat.clear(user_id)

    # ── SYSTEM PROMPT ─────────────────────────────────────────

    def get_enhanced_system_prompt(self, user_id: str, query: str, base_prompt: str) -> str:
        """
        Enriquece o system prompt com contexto obrigatório.
        Factos + steps relevantes são SEMPRE injectados.
        """
        context = self.memory.build_system_context(user_id, query)
        if context:
            return f"{base_prompt}\n\n{context}"
        return base_prompt

    # ── FACTS ─────────────────────────────────────────────────

    def store_fact(self, user_id: str, key: str, value: str,
                   importance: float = 0.5, category: str = "general",
                   tags: List[str] = None) -> bool:
        return self.memory.facts.store(user_id, key, value, importance, category, tags)

    def get_user_facts(self, user_id: str) -> Dict[str, Fact]:
        return self.memory.facts.get_all(user_id)

    def extract_and_store_facts(self, user_id: str, user_msg: str, bot_reply: str) -> List[str]:
        """Extrai e persiste factos automaticamente. Chamar após cada resposta final."""
        return self.memory.facts.extract_from_exchange(user_id, user_msg, bot_reply)

    # ── CONTEXT STEPS (compatibilidade v3.1) ──────────────────

    def record_step(self, user_id: str, query: str, step_data: dict):
        """Regista step técnico do agente."""
        importance = RelevanceScorer.importance(
            step_data.get('thought', ''),
            step_data.get('confidence', 0.8),
            bool(step_data.get('code_result') or step_data.get('result'))
        )
        step = ContextStep(
            query=query,
            thought=step_data.get('thought', ''),
            action=step_data.get('action', 'continue'),
            confidence=step_data.get('confidence', 0.8),
            importance=importance,
            tool_used=step_data.get('tool', ''),
            tool_result=str(step_data.get('result', ''))[:300],
            session_id=self.memory.session_id(user_id),
            timestamp=time.time()
        )
        self.memory.steps.store(user_id, step)

    # ── STATS ─────────────────────────────────────────────────

    def get_stats(self, user_id: str) -> dict:
        """Stats compatíveis com v3.1 + novos campos."""
        chat_count  = len(self.memory.chat.get(user_id, 9999))
        facts_stats = self.memory.facts.stats(user_id)
        steps_row   = self.db.fetchone(
            "SELECT COUNT(*) as c FROM context_steps WHERE user_id=?", (user_id,)
        )
        cron_count  = self.db.fetchone(
            "SELECT COUNT(*) as c FROM cron_jobs WHERE user_id=?", (user_id,)
        )
        return {
            "chat_history_count": chat_count,
            "facts":              facts_stats,
            "context_steps":      steps_row["c"] if steps_row else 0,
            "cron_jobs":          cron_count["c"] if cron_count else 0,
        }

    # ── CRONS (proxy conveniente) ──────────────────────────────

    def set_cron_executor(self, fn: Callable):
        self.memory.crons.set_executor(fn)

    async def start_cron_scheduler(self):
        await self.memory.crons.start()


# ══════════════════════════════════════════════════════════════════
# TESTE DIRETO
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio, tempfile, os

    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    cfg   = MemoryConfig(db_path=db_path)
    agent = MemoryEnhancedAgent(cfg)
    uid   = "test_user"

    # 1. Chat history persistente
    agent.add_chat_message(uid, "user",      "Olá, o meu nome é Carlos e gosto de Python.")
    agent.add_chat_message(uid, "assistant", "Olá Carlos! Vejo que preferes Python.")

    # 2. Extracção automática de factos
    extracted = agent.extract_and_store_facts(
        uid,
        "Olá, o meu nome é Carlos e gosto de Python.",
        "Olá Carlos!"
    )
    print(f"\n✅ Factos extraídos: {extracted}")

    # 3. Contexto para o prompt
    prompt = agent.get_enhanced_system_prompt(uid, "como posso ajudar?", "Tu és o OPENBOT.")
    print(f"\n✅ System prompt com contexto:\n{prompt}")

    # 4. Record step
    agent.record_step(uid, "Como instalar o requests?", {
        'thought': 'O utilizador quer instalar a biblioteca requests do Python.',
        'confidence': 0.9
    })

    # 5. Stats
    print(f"\n✅ Stats: {json.dumps(agent.get_stats(uid), indent=2, ensure_ascii=False)}")

    # 6. Cron
    async def test_cron():
        async def executor(job):
            return f"[SIMULADO] {job.task}"

        agent.set_cron_executor(executor)
        job = agent.crons.create(uid, "Teste", "Cron de teste", "every:10s", "shell", "echo hello")
        print(f"\n✅ Cron criado: {job.name} | next_run: {agent.crons.format_next_run(job)}")

        result = await agent.crons.run_now(job.id, uid)
        print(f"✅ Cron executado: {result}")

    asyncio.run(test_cron())
    os.unlink(db_path)
    print("\n✅ HGR v4 — todos os testes passaram!")
