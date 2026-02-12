#!/usr/bin/env python3
"""
ROKO Reasoning Agent - Enhanced with Hierarchical Memory System
Version 2.0 - Without FAISS, using simple but effective memory hierarchy

Improvements:
- 3-tier memory system (Short/Medium/Long)
- Session management
- Intelligent context pruning
- Query relevance scoring
- Memory consolidation
- No external dependencies (FAISS-free)
"""

import os
import json
import time
import hashlib
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
import sqlite3
import re

# ────────────────────────────────────────────────────────────────
# MEMORY SYSTEM CONFIGURATION
# ────────────────────────────────────────────────────────────────

@dataclass
class MemoryConfig:
    """Configuration for memory tiers"""
    # Short-term memory (last N interactions)
    short_term_size: int = 10
    short_term_ttl: int = 300  # 5 minutes
    
    # Medium-term memory (summarized sessions)
    medium_term_size: int = 50
    medium_term_ttl: int = 3600  # 1 hour
    
    # Long-term memory (persistent important facts)
    long_term_db: str = "agent_memory.db"
    
    # Relevance thresholds
    min_relevance_score: float = 0.3
    importance_threshold: float = 0.7


# ────────────────────────────────────────────────────────────────
# SIMPLE RELEVANCE SCORING (No ML required)
# ────────────────────────────────────────────────────────────────

class SimpleRelevanceScorer:
    """Simple keyword-based relevance scoring without ML"""
    
    @staticmethod
    def extract_keywords(text: str) -> set:
        """Extract important keywords from text"""
        # Remove common stop words
        stop_words = {
            'o', 'a', 'de', 'da', 'do', 'para', 'com', 'em', 'um', 'uma',
            'the', 'is', 'and', 'or', 'to', 'in', 'of', 'for', 'on', 'at'
        }
        
        # Tokenize and clean
        words = re.findall(r'\b\w+\b', text.lower())
        keywords = {w for w in words if len(w) > 3 and w not in stop_words}
        
        return keywords
    
    @staticmethod
    def calculate_relevance(query: str, memory_text: str) -> float:
        """
        Calculate relevance score between query and memory.
        Returns score between 0.0 and 1.0
        """
        query_keywords = SimpleRelevanceScorer.extract_keywords(query)
        memory_keywords = SimpleRelevanceScorer.extract_keywords(memory_text)
        
        if not query_keywords or not memory_keywords:
            return 0.0
        
        # Jaccard similarity
        intersection = len(query_keywords & memory_keywords)
        union = len(query_keywords | memory_keywords)
        
        return intersection / union if union > 0 else 0.0
    
    @staticmethod
    def calculate_importance(thought: str, confidence: float, has_code: bool) -> float:
        """Calculate importance score for a memory"""
        base_score = confidence
        
        # Boost for certain keywords
        important_words = {'error', 'critical', 'important', 'bug', 'fix', 'solution'}
        text_lower = thought.lower()
        
        keyword_boost = sum(0.1 for word in important_words if word in text_lower)
        code_boost = 0.2 if has_code else 0.0
        
        return min(1.0, base_score + keyword_boost + code_boost)


# ────────────────────────────────────────────────────────────────
# MEMORY STRUCTURES
# ────────────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """Single memory entry"""
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
            'timestamp': self.timestamp,
            'query': self.query,
            'thought': self.thought,
            'action': self.action,
            'confidence': self.confidence,
            'code_result': self.code_result,
            'importance': self.importance,
            'session_id': self.session_id
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


@dataclass
class Session:
    """User session with metadata"""
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


# ────────────────────────────────────────────────────────────────
# HIERARCHICAL MEMORY MANAGER
# ────────────────────────────────────────────────────────────────

class HierarchicalMemoryManager:
    """
    3-Tier memory system without FAISS:
    - Short-term: Recent interactions (in-memory deque)
    - Medium-term: Session summaries (in-memory dict)
    - Long-term: Important facts (SQLite)
    """
    
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.scorer = SimpleRelevanceScorer()
        
        # Short-term: Last N interactions per user
        self.short_term: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=config.short_term_size)
        )
        
        # Medium-term: Active sessions
        self.sessions: Dict[str, Session] = {}
        
        # Long-term: SQLite database
        self._init_long_term_db()
        
        # Logging
        self.logger = logging.getLogger(__name__)
    
    def _init_long_term_db(self):
        """Initialize SQLite database for long-term memory"""
        self.db_conn = sqlite3.connect(
            self.config.long_term_db,
            check_same_thread=False
        )
        
        cursor = self.db_conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS long_term_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                user_id TEXT,
                query TEXT,
                thought TEXT,
                action TEXT,
                confidence REAL,
                importance REAL,
                code_result TEXT,
                session_id TEXT,
                keywords TEXT
            )
        """)
        
        # Index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_importance 
            ON long_term_memory(user_id, importance DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_keywords 
            ON long_term_memory(keywords)
        """)
        
        self.db_conn.commit()
    
    # ────────────────────────────────────────────────────────
    # SESSION MANAGEMENT
    # ────────────────────────────────────────────────────────
    
    def get_or_create_session(self, user_id: str) -> Session:
        """Get existing session or create new one"""
        # Clean expired sessions first
        self._cleanup_expired_sessions()
        
        # Find active session
        for session in self.sessions.values():
            if session.user_id == user_id and not session.is_expired(
                self.config.medium_term_ttl
            ):
                return session
        
        # Create new session
        session_id = hashlib.md5(
            f"{user_id}{time.time()}".encode()
        ).hexdigest()[:12]
        
        session = Session(
            session_id=session_id,
            user_id=user_id,
            started_at=time.time(),
            last_activity=time.time()
        )
        
        self.sessions[session_id] = session
        self.logger.info(f"Created new session {session_id} for user {user_id}")
        
        return session
    
    def _cleanup_expired_sessions(self):
        """Remove expired sessions"""
        expired = [
            sid for sid, session in self.sessions.items()
            if session.is_expired(self.config.medium_term_ttl)
        ]
        
        for sid in expired:
            # Consolidate to long-term before removing
            self._consolidate_session(self.sessions[sid])
            del self.sessions[sid]
            self.logger.info(f"Cleaned up expired session {sid}")
    
    # ────────────────────────────────────────────────────────
    # MEMORY STORAGE
    # ────────────────────────────────────────────────────────
    
    def store_memory(
        self,
        user_id: str,
        query: str,
        thought: str,
        action: str,
        confidence: float,
        code_result: Optional[str] = None
    ):
        """Store memory in appropriate tier(s)"""
        
        # Calculate importance
        importance = self.scorer.calculate_importance(
            thought, confidence, code_result is not None
        )
        
        # Get session
        session = self.get_or_create_session(user_id)
        
        # Create memory entry
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
        
        # Always store in short-term
        self.short_term[user_id].append(memory)
        
        # Store in session (medium-term)
        session.add_memory(memory)
        
        # Store important memories in long-term
        if importance >= self.config.importance_threshold:
            self._store_long_term(user_id, memory)
            self.logger.info(
                f"Stored high-importance memory (score: {importance:.2f})"
            )
    
    def _store_long_term(self, user_id: str, memory: MemoryEntry):
        """Store memory in SQLite long-term database"""
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
            memory.timestamp,
            user_id,
            memory.query,
            memory.thought,
            memory.action,
            memory.confidence,
            memory.importance,
            memory.code_result,
            memory.session_id,
            keywords
        ))
        self.db_conn.commit()
    
    # ────────────────────────────────────────────────────────
    # MEMORY RETRIEVAL
    # ────────────────────────────────────────────────────────
    
    def retrieve_relevant_context(
        self,
        user_id: str,
        current_query: str,
        max_memories: int = 5
    ) -> List[MemoryEntry]:
        """
        Retrieve most relevant memories from all tiers.
        Returns combined context prioritized by relevance and recency.
        """
        candidates = []
        
        # 1. Short-term memories (most recent)
        for memory in self.short_term.get(user_id, []):
            relevance = self.scorer.calculate_relevance(
                current_query, 
                memory.query + ' ' + memory.thought
            )
            
            if relevance >= self.config.min_relevance_score:
                # Boost recent memories
                recency_boost = 0.2
                score = relevance + recency_boost
                candidates.append((score, memory, 'short'))
        
        # 2. Medium-term (session context)
        session = self.get_or_create_session(user_id)
        for memory in session.memories:
            relevance = self.scorer.calculate_relevance(
                current_query,
                memory.query + ' ' + memory.thought
            )
            
            if relevance >= self.config.min_relevance_score:
                score = relevance + 0.1  # Small recency boost
                candidates.append((score, memory, 'medium'))
        
        # 3. Long-term (important memories)
        long_term_memories = self._retrieve_long_term(user_id, current_query)
        for memory in long_term_memories:
            relevance = self.scorer.calculate_relevance(
                current_query,
                memory.query + ' ' + memory.thought
            )
            
            if relevance >= self.config.min_relevance_score:
                # Importance boost
                score = relevance + (memory.importance * 0.3)
                candidates.append((score, memory, 'long'))
        
        # Sort by score and deduplicate
        candidates.sort(key=lambda x: x[0], reverse=True)
        
        # Take top N, ensuring diversity
        selected = []
        seen_thoughts = set()
        
        for score, memory, tier in candidates:
            thought_hash = hashlib.md5(memory.thought.encode()).hexdigest()
            
            if thought_hash not in seen_thoughts:
                selected.append(memory)
                seen_thoughts.add(thought_hash)
            
            if len(selected) >= max_memories:
                break
        
        self.logger.info(
            f"Retrieved {len(selected)} relevant memories for query: {current_query[:50]}"
        )
        
        return selected
    
    def _retrieve_long_term(
        self,
        user_id: str,
        query: str,
        limit: int = 10
    ) -> List[MemoryEntry]:
        """Retrieve from long-term SQLite database"""
        
        # Extract keywords from query
        keywords = self.scorer.extract_keywords(query)
        
        cursor = self.db_conn.cursor()
        
        # Simple keyword matching
        memories = []
        for keyword in list(keywords)[:5]:  # Limit keywords
            cursor.execute("""
                SELECT timestamp, query, thought, action, confidence,
                       importance, code_result, session_id
                FROM long_term_memory
                WHERE user_id = ? 
                  AND keywords LIKE ?
                ORDER BY importance DESC, timestamp DESC
                LIMIT ?
            """, (user_id, f'%{keyword}%', limit))
            
            for row in cursor.fetchall():
                memory = MemoryEntry(
                    timestamp=row[0],
                    query=row[1],
                    thought=row[2],
                    action=row[3],
                    confidence=row[4],
                    importance=row[5],
                    code_result=row[6],
                    session_id=row[7]
                )
                memories.append(memory)
        
        # Deduplicate
        unique_memories = {m.thought: m for m in memories}
        return list(unique_memories.values())[:limit]
    
    # ────────────────────────────────────────────────────────
    # MEMORY CONSOLIDATION
    # ────────────────────────────────────────────────────────
    
    def _consolidate_session(self, session: Session):
        """
        Consolidate session memories before expiration.
        Extract important patterns and store in long-term.
        """
        if not session.memories:
            return
        
        # Calculate session statistics
        avg_confidence = sum(m.confidence for m in session.memories) / len(session.memories)
        
        # Find high-value memories
        important = [
            m for m in session.memories 
            if m.importance >= self.config.importance_threshold
        ]
        
        # Store important ones in long-term if not already there
        for memory in important:
            # Check if already stored
            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM long_term_memory
                WHERE session_id = ? AND timestamp = ?
            """, (session.session_id, memory.timestamp))
            
            if cursor.fetchone()[0] == 0:
                self._store_long_term(session.user_id, memory)
        
        self.logger.info(
            f"Consolidated session {session.session_id}: "
            f"{len(important)}/{len(session.memories)} memories stored"
        )
    
    # ────────────────────────────────────────────────────────
    # CONTEXT FORMATTING
    # ────────────────────────────────────────────────────────
    
    def format_context_for_prompt(
        self,
        user_id: str,
        current_query: str
    ) -> str:
        """
        Format relevant memories into context string for LLM prompt.
        """
        memories = self.retrieve_relevant_context(user_id, current_query)
        
        if not memories:
            return "Nenhum contexto anterior relevante."
        
        context_parts = ["Contexto relevante de interações anteriores:\n"]
        
        for i, memory in enumerate(memories, 1):
            age = time.time() - memory.timestamp
            age_str = f"{int(age/60)}min atrás" if age < 3600 else f"{int(age/3600)}h atrás"
            
            context_parts.append(
                f"\n{i}. [{age_str}] Query: {memory.query}\n"
                f"   Pensamento: {memory.thought}\n"
                f"   Confiança: {memory.confidence:.0%}"
            )
            
            if memory.code_result:
                context_parts.append(f"   Código executado: {memory.code_result[:100]}...")
        
        return '\n'.join(context_parts)
    
    # ────────────────────────────────────────────────────────
    # STATISTICS & MONITORING
    # ────────────────────────────────────────────────────────
    
    def get_memory_stats(self, user_id: str) -> dict:
        """Get memory statistics for user"""
        cursor = self.db_conn.cursor()
        
        # Long-term count
        cursor.execute(
            "SELECT COUNT(*) FROM long_term_memory WHERE user_id = ?",
            (user_id,)
        )
        long_term_count = cursor.fetchone()[0]
        
        # Session info
        session = self.get_or_create_session(user_id)
        
        return {
            'short_term_count': len(self.short_term.get(user_id, [])),
            'session_count': len(session.memories),
            'long_term_count': long_term_count,
            'active_session_id': session.session_id,
            'session_age_minutes': int((time.time() - session.started_at) / 60)
        }
    
    def cleanup_old_memories(self, days: int = 30):
        """Remove memories older than N days from long-term"""
        cutoff = time.time() - (days * 24 * 3600)
        
        cursor = self.db_conn.cursor()
        cursor.execute(
            "DELETE FROM long_term_memory WHERE timestamp < ?",
            (cutoff,)
        )
        deleted = cursor.rowcount
        self.db_conn.commit()
        
        self.logger.info(f"Cleaned up {deleted} old memories")
        return deleted


# ────────────────────────────────────────────────────────────────
# ENHANCED AGENT WITH MEMORY
# ────────────────────────────────────────────────────────────────

class MemoryEnhancedAgent:
    """
    Reasoning agent enhanced with hierarchical memory system.
    Integrates seamlessly with existing agent_loop.
    """
    
    def __init__(self, memory_config: Optional[MemoryConfig] = None):
        self.memory = HierarchicalMemoryManager(
            memory_config or MemoryConfig()
        )
        self.logger = logging.getLogger(__name__)
    
    def get_enhanced_system_prompt(
        self,
        user_id: str,
        current_query: str,
        base_prompt: str
    ) -> str:
        """
        Enhance system prompt with relevant memory context.
        """
        context = self.memory.format_context_for_prompt(user_id, current_query)
        
        enhanced_prompt = f"""{base_prompt}

{context}

Importante: Use o contexto acima para evitar repetir trabalho já feito 
e manter consistência com interações anteriores.
"""
        return enhanced_prompt
    
    def record_step(
        self,
        user_id: str,
        query: str,
        step_data: dict
    ):
        """
        Record agent step in memory system.
        Call this after each agent loop iteration.
        """
        self.memory.store_memory(
            user_id=user_id,
            query=query,
            thought=step_data.get('thought', ''),
            action=step_data.get('action', 'continue'),
            confidence=step_data.get('confidence', 0.5),
            code_result=step_data.get('code_result')
        )
    
    def get_stats(self, user_id: str) -> dict:
        """Get memory statistics for user"""
        return self.memory.get_memory_stats(user_id)


# ────────────────────────────────────────────────────────────────
# USAGE EXAMPLE
# ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s'
    )
    
    # Initialize agent with memory
    config = MemoryConfig(
        short_term_size=10,
        medium_term_size=50,
        min_relevance_score=0.3
    )
    
    agent = MemoryEnhancedAgent(config)
    
    # Example usage
    user_id = "user_123"
    
    # First query
    query1 = "Quanto é 17 × 42?"
    
    # Record some steps
    agent.record_step(user_id, query1, {
        'thought': 'Vou calcular 17 × 42',
        'action': 'execute_code',
        'confidence': 0.95,
        'code_result': '714'
    })
    
    # Second query (related)
    query2 = "E quanto é 17 × 43?"
    
    # Get enhanced prompt with context
    base_prompt = "Você é um agente matemático..."
    enhanced_prompt = agent.get_enhanced_system_prompt(
        user_id, query2, base_prompt
    )
    
    print("Enhanced Prompt:")
    print(enhanced_prompt)
    
    # Get stats
    stats = agent.get_stats(user_id)
    print("\nMemory Stats:", json.dumps(stats, indent=2))
