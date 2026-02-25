#!/usr/bin/env python3
"""
OPENBOT v3.1 — HGR (Hierarchical Grounded Reasoning) Memory System
Versão corrigida com:
  - FIX #1: chat_history real por usuário (não só steps técnicos)
  - FIX #2: add_chat_message / get_chat_history exposto no MemoryEnhancedAgent
  - FIX #3: importance_threshold 0.7→0.3, min_relevance 0.3→0.1, confidence 0.5→0.8
  - FIX #4: short_term_ttl 5min→1h, medium_term_ttl 1h→24h
"""

import os
import json
import time
import hashlib
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
import sqlite3
import re

# ─────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DE MEMÓRIA
# ─────────────────────────────────────────────────────────────────

@dataclass
class MemoryConfig:
    """Configuração dos 3 níveis de memória"""

    # Short-term (RAM — deque)
    short_term_size: int        = 30       # FIX #4: era 10
    short_term_ttl: int         = 3600     # FIX #4: era 300 (5min) → 1h

    # Medium-term (sessão RAM)
    medium_term_size: int       = 100      # FIX #4: era 50
    medium_term_ttl: int        = 86400    # FIX #4: era 3600 (1h) → 24h

    # Long-term (SQLite persistente)
    long_term_db: str           = "agent_memory.db"

    # Relevância
    min_relevance_score: float  = 0.1     # FIX #3: era 0.3
    importance_threshold: float = 0.3     # FIX #3: era 0.7

    # Chat history
    max_chat_history: int       = 100     # máx mensagens em RAM por usuário
    chat_history_to_llm: int    = 40      # quantas enviar ao LLM por requisição


# ─────────────────────────────────────────────────────────────────
# RELEVÂNCIA SIMPLES (sem ML)
# ─────────────────────────────────────────────────────────────────

class SimpleRelevanceScorer:

    @staticmethod
    def extract_keywords(text: str) -> set:
        stop_words = {
            'o', 'a', 'de', 'da', 'do', 'para', 'com', 'em', 'um', 'uma',
            'the', 'is', 'and', 'or', 'to', 'in', 'of', 'for', 'on', 'at',
            'que', 'se', 'por', 'mas', 'como', 'foi', 'ser', 'tem', 'sao'
        }
        words = re.findall(r'\b\w+\b', text.lower())
        return {w for w in words if len(w) > 3 and w not in stop_words}

    @staticmethod
    def calculate_relevance(query: str, memory_text: str) -> float:
        q_kw = SimpleRelevanceScorer.extract_keywords(query)
        m_kw = SimpleRelevanceScorer.extract_keywords(memory_text)
        if not q_kw or not m_kw:
            return 0.0
        intersection = len(q_kw & m_kw)
        union = len(q_kw | m_kw)
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def calculate_importance(thought: str, confidence: float, has_code: bool) -> float:
        important_words = {
            'error', 'critical', 'important', 'bug', 'fix', 'solution',
            'erro', 'problema', 'solucao', 'importante', 'critico'
        }
        text_lower = thought.lower()
        keyword_boost = sum(0.1 for w in important_words if w in text_lower)
        code_boost = 0.2 if has_code else 0.0
        return min(1.0, confidence + keyword_boost + code_boost)


# ─────────────────────────────────────────────────────────────────
# ESTRUTURAS DE DADOS
# ─────────────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    timestamp: float
    query: str
    thought: str
    action: str
    confidence: float
    code_result: Optional[str] = None
    importance: float = 0.0
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'timestamp':   self.timestamp,
            'query':       self.query,
            'thought':     self.thought,
            'action':      self.action,
            'confidence':  self.confidence,
            'code_result': self.code_result,
            'importance':  self.importance,
            'session_id':  self.session_id
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


@dataclass
class ChatMessage:
    """FIX #1: Mensagem real do dialogo (user ou assistant)"""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_llm_format(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class Session:
    session_id: str
    user_id: str
    started_at: float
    last_activity: float
    memories: deque = field(default_factory=lambda: deque(maxlen=10))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, ttl: int) -> bool:
        return time.time() - self.last_activity > ttl

    def add_memory(self, memory: MemoryEntry):
        self.memories.append(memory)
        self.last_activity = time.time()


# ─────────────────────────────────────────────────────────────────
# GERENCIADOR DE MEMORIA HIERARQUICA
# ─────────────────────────────────────────────────────────────────

class HierarchicalMemoryManager:
    """
    3 niveis de memoria:
      Short-term  - deque RAM (ultimas N interacoes)
      Medium-term - sessao RAM (ativa por 24h)
      Long-term   - SQLite (persistente)

    FIX #1: Adicionado chat_history separado que armazena o dialogo real
            user/assistant para ser passado ao LLM a cada requisicao.
    """

    def __init__(self, config: MemoryConfig):
        self.config  = config
        self.scorer  = SimpleRelevanceScorer()
        self.logger  = logging.getLogger(__name__)

        # Short-term: deque por usuario
        self.short_term: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=config.short_term_size)
        )

        # Medium-term: sessoes ativas
        self.sessions: Dict[str, Session] = {}

        # FIX #1: Historico de chat real por usuario
        self.chat_history: Dict[str, List[ChatMessage]] = defaultdict(list)

        # Long-term: SQLite
        self._init_long_term_db()

    # ── CHAT HISTORY ──────────────────────────────────────────

    def add_chat_message(self, user_id: str, role: str, content: str):
        """Registra mensagem real do dialogo (user ou assistant)."""
        self.chat_history[user_id].append(
            ChatMessage(role=role, content=content)
        )
        if len(self.chat_history[user_id]) > self.config.max_chat_history:
            self.chat_history[user_id] = self.chat_history[user_id][-self.config.max_chat_history:]

    def get_chat_history(self, user_id: str, last_n: int = None) -> List[dict]:
        """Retorna historico no formato messages da API."""
        n = last_n or self.config.chat_history_to_llm
        history = self.chat_history.get(user_id, [])
        return [msg.to_llm_format() for msg in history[-n:]]

    def clear_chat_history(self, user_id: str) -> int:
        """Limpa historico de chat. Retorna quantidade removida."""
        if user_id in self.chat_history:
            count = len(self.chat_history[user_id])
            self.chat_history[user_id] = []
            return count
        return 0

    # ── SQLITE ────────────────────────────────────────────────

    def _init_long_term_db(self):
        self.db_conn = sqlite3.connect(
            self.config.long_term_db,
            check_same_thread=False
        )
        cursor = self.db_conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS long_term_memory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   REAL,
                user_id     TEXT,
                query       TEXT,
                thought     TEXT,
                action      TEXT,
                confidence  REAL,
                importance  REAL,
                code_result TEXT,
                session_id  TEXT,
                keywords    TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_importance
            ON long_term_memory(user_id, importance DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_keywords
            ON long_term_memory(keywords)
        """)
        self.db_conn.commit()

    # ── SESSOES ───────────────────────────────────────────────

    def get_or_create_session(self, user_id: str) -> Session:
        self._cleanup_expired_sessions()
        for session in self.sessions.values():
            if session.user_id == user_id and not session.is_expired(self.config.medium_term_ttl):
                return session
        session_id = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:12]
        session = Session(
            session_id=session_id,
            user_id=user_id,
            started_at=time.time(),
            last_activity=time.time()
        )
        self.sessions[session_id] = session
        self.logger.info(f"Nova sessao {session_id} para {user_id}")
        return session

    def _cleanup_expired_sessions(self):
        expired = [
            sid for sid, s in self.sessions.items()
            if s.is_expired(self.config.medium_term_ttl)
        ]
        for sid in expired:
            self._consolidate_session(self.sessions[sid])
            del self.sessions[sid]

    # ── ARMAZENAMENTO ─────────────────────────────────────────

    def store_memory(
        self,
        user_id: str,
        query: str,
        thought: str,
        action: str,
        confidence: float,
        code_result: Optional[str] = None
    ):
        importance = self.scorer.calculate_importance(
            thought, confidence, code_result is not None
        )
        session = self.get_or_create_session(user_id)
        memory = MemoryEntry(
            timestamp=time.time(),
            query=query,
            thought=thought,
            action=action,
            confidence=confidence,
            code_result=code_result,
            importance=importance,
            session_id=session.session_id
        )
        self.short_term[user_id].append(memory)
        session.add_memory(memory)
        if importance >= self.config.importance_threshold:
            self._store_long_term(user_id, memory)

    def _store_long_term(self, user_id: str, memory: MemoryEntry):
        keywords = ' '.join(
            self.scorer.extract_keywords(memory.query + ' ' + memory.thought)
        )
        cursor = self.db_conn.cursor()
        cursor.execute("""
            INSERT INTO long_term_memory
            (timestamp, user_id, query, thought, action, confidence,
             importance, code_result, session_id, keywords)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            memory.timestamp, user_id, memory.query, memory.thought,
            memory.action, memory.confidence, memory.importance,
            memory.code_result, memory.session_id, keywords
        ))
        self.db_conn.commit()

    # ── RECUPERACAO DE CONTEXTO ───────────────────────────────

    def retrieve_relevant_context(
        self,
        user_id: str,
        current_query: str,
        max_memories: int = 5
    ) -> List[MemoryEntry]:
        candidates = []

        for memory in self.short_term.get(user_id, []):
            relevance = self.scorer.calculate_relevance(
                current_query, memory.query + ' ' + memory.thought
            )
            if relevance >= self.config.min_relevance_score:
                candidates.append((relevance + 0.2, memory, 'short'))

        session = self.get_or_create_session(user_id)
        for memory in session.memories:
            relevance = self.scorer.calculate_relevance(
                current_query, memory.query + ' ' + memory.thought
            )
            if relevance >= self.config.min_relevance_score:
                candidates.append((relevance + 0.1, memory, 'medium'))

        for memory in self._retrieve_long_term(user_id, current_query):
            relevance = self.scorer.calculate_relevance(
                current_query, memory.query + ' ' + memory.thought
            )
            if relevance >= self.config.min_relevance_score:
                candidates.append((relevance + memory.importance * 0.3, memory, 'long'))

        candidates.sort(key=lambda x: x[0], reverse=True)
        selected = []
        seen = set()
        for _, memory, _ in candidates:
            h = hashlib.md5(memory.thought.encode()).hexdigest()
            if h not in seen:
                selected.append(memory)
                seen.add(h)
            if len(selected) >= max_memories:
                break
        return selected

    def _retrieve_long_term(self, user_id: str, query: str, limit: int = 10) -> List[MemoryEntry]:
        keywords = self.scorer.extract_keywords(query)
        cursor = self.db_conn.cursor()
        memories = []
        for keyword in list(keywords)[:5]:
            cursor.execute("""
                SELECT timestamp, query, thought, action, confidence,
                       importance, code_result, session_id
                FROM long_term_memory
                WHERE user_id = ? AND keywords LIKE ?
                ORDER BY importance DESC, timestamp DESC
                LIMIT ?
            """, (user_id, f'%{keyword}%', limit))
            for row in cursor.fetchall():
                memories.append(MemoryEntry(
                    timestamp=row[0], query=row[1], thought=row[2],
                    action=row[3], confidence=row[4], importance=row[5],
                    code_result=row[6], session_id=row[7]
                ))
        unique = {m.thought: m for m in memories}
        return list(unique.values())[:limit]

    # ── CONSOLIDACAO ──────────────────────────────────────────

    def _consolidate_session(self, session: Session):
        if not session.memories:
            return
        important = [m for m in session.memories if m.importance >= self.config.importance_threshold]
        for memory in important:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM long_term_memory
                WHERE session_id = ? AND timestamp = ?
            """, (session.session_id, memory.timestamp))
            if cursor.fetchone()[0] == 0:
                self._store_long_term(session.user_id, memory)
        self.logger.info(
            f"Sessao {session.session_id} consolidada: {len(important)}/{len(session.memories)}"
        )

    # ── FORMAT PARA SYSTEM PROMPT ─────────────────────────────

    def format_context_for_prompt(self, user_id: str, current_query: str) -> str:
        """
        Contexto de sessoes anteriores para o system prompt.
        O historico atual ja vai nas messages — nao duplicar aqui.
        """
        memories = self.retrieve_relevant_context(user_id, current_query)
        if not memories:
            return ""

        parts = ["=== Contexto de sessoes anteriores ==="]
        for i, m in enumerate(memories, 1):
            age = time.time() - m.timestamp
            age_str = f"{int(age/60)}min atras" if age < 3600 else f"{int(age/3600)}h atras"
            parts.append(
                f"\n{i}. [{age_str}] Pergunta: {m.query}\n"
                f"   Contexto: {m.thought[:200]}\n"
                f"   Confianca: {m.confidence:.0%}"
            )
            if m.code_result:
                parts.append(f"   Resultado: {m.code_result[:150]}...")
        parts.append("======================================")
        return '\n'.join(parts)

    # ── ESTATISTICAS ──────────────────────────────────────────

    def get_memory_stats(self, user_id: str) -> dict:
        cursor = self.db_conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM long_term_memory WHERE user_id = ?", (user_id,)
        )
        long_term_count = cursor.fetchone()[0]
        session = self.get_or_create_session(user_id)
        return {
            'short_term_count':    len(self.short_term.get(user_id, [])),
            'session_count':       len(session.memories),
            'long_term_count':     long_term_count,
            'chat_history_count':  len(self.chat_history.get(user_id, [])),
            'active_session_id':   session.session_id,
            'session_age_minutes': int((time.time() - session.started_at) / 60)
        }

    def cleanup_old_memories(self, days: int = 30) -> int:
        cutoff = time.time() - (days * 24 * 3600)
        cursor = self.db_conn.cursor()
        cursor.execute("DELETE FROM long_term_memory WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount
        self.db_conn.commit()
        return deleted


# ─────────────────────────────────────────────────────────────────
# AGENTE COM MEMORIA — interface principal usada pelo OPENBOT
# ─────────────────────────────────────────────────────────────────

class MemoryEnhancedAgent:
    """
    Interface de alto nivel entre o agent_loop (OPENBOT.py) e o sistema de memoria.
    """

    def __init__(self, memory_config: Optional[MemoryConfig] = None):
        self.memory = HierarchicalMemoryManager(memory_config or MemoryConfig())
        self.logger = logging.getLogger(__name__)

    # ── CHAT HISTORY (FIX #1 e #2) ───────────────────────────

    def add_chat_message(self, user_id: str, role: str, content: str):
        """Registra mensagem real do dialogo (user ou assistant)."""
        self.memory.add_chat_message(user_id, role, content)

    def get_chat_history(self, user_id: str, last_n: int = None) -> List[dict]:
        """Retorna historico de chat no formato messages da API."""
        return self.memory.get_chat_history(user_id, last_n)

    def clear_chat_history(self, user_id: str) -> int:
        """Limpa historico de chat (nova conversa). Retorna qtd removida."""
        return self.memory.clear_chat_history(user_id)

    # ── SYSTEM PROMPT ENRIQUECIDO ─────────────────────────────

    def get_enhanced_system_prompt(
        self,
        user_id: str,
        current_query: str,
        base_prompt: str
    ) -> str:
        context = self.memory.format_context_for_prompt(user_id, current_query)
        if context:
            return f"{base_prompt}\n\n{context}\n"
        return base_prompt

    # ── RECORD STEP ───────────────────────────────────────────

    def record_step(self, user_id: str, query: str, step_data: dict):
        """Registra step tecnico do agente. FIX #3: confidence padrao 0.5 -> 0.8"""
        self.memory.store_memory(
            user_id=user_id,
            query=query,
            thought=step_data.get('thought', ''),
            action=step_data.get('action', 'continue'),
            confidence=step_data.get('confidence', 0.8),
            code_result=step_data.get('code_result')
        )

    # ── STATS ─────────────────────────────────────────────────

    def get_stats(self, user_id: str) -> dict:
        return self.memory.get_memory_stats(user_id)


# ─────────────────────────────────────────────────────────────────
# TESTE DIRETO
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

    config = MemoryConfig(short_term_size=10, medium_term_size=50)
    agent  = MemoryEnhancedAgent(config)
    uid    = "user_test"

    agent.add_chat_message(uid, "user", "Meu nome e Carlos")
    agent.add_chat_message(uid, "assistant", "Ola Carlos! Como posso ajudar?")
    agent.add_chat_message(uid, "user", "Qual meu nome?")

    history = agent.get_chat_history(uid)
    print("\n Chat History:")
    for msg in history:
        print(f"  [{msg['role']}] {msg['content']}")

    agent.record_step(uid, "Qual meu nome?", {
        'thought': 'O usuario disse que se chama Carlos.',
        'action': 'respond',
        'confidence': 0.95
    })

    stats = agent.get_stats(uid)
    print("\n Stats:", json.dumps(stats, indent=2))
