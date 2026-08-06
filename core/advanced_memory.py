"""
J.A.R.V.I.S. Advanced Memory System
Semantic search, automatic memory consolidation, and context awareness.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Types of memories the system can store."""
    CONVERSATION = "conversation"  # Past conversations
    CONTEXT = "context"  # Current conversation context
    PREFERENCE = "preference"  # User preferences
    SKILL = "skill"  # Learned skills and patterns
    ERROR = "error"  # Error patterns and solutions
    WORKFLOW = "workflow"  # Common workflows
    RELATIONSHIP = "relationship"  # Entity relationships
    EVENT = "event"  # Important events


@dataclass
class MemoryEntry:
    """A single memory entry with metadata."""
    id: str
    content: str
    memory_type: MemoryType
    created_at: datetime
    updated_at: datetime
    relevance_score: float = 1.0
    tags: List[str] = None
    metadata: Dict[str, Any] = None
    embedding: List[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "relevance_score": self.relevance_score,
            "tags": self.tags or [],
            "metadata": self.metadata or {},
        }


class EnhancedMemoryManager:
    """Advanced memory management with semantic search and consolidation."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(
            os.path.expanduser("~"), ".jarvis", "memory", "advanced_memory.db"
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self._init_database()
        self._memory_cache: Dict[str, MemoryEntry] = {}
        self.max_cache_size = 1000
    
    def _init_database(self):
        """Initialize the memory database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Main memory table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                relevance_score REAL DEFAULT 1.0,
                tags TEXT,
                metadata TEXT,
                access_count INTEGER DEFAULT 0,
                last_accessed DATETIME,
                FOREIGN KEY(memory_type) REFERENCES memory_types(type)
            )
        ''')
        
        # Memory relationships (for knowledge graphs)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_relationships (
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (from_id, to_id, relationship_type),
                FOREIGN KEY(from_id) REFERENCES memories(id),
                FOREIGN KEY(to_id) REFERENCES memories(id)
            )
        ''')
        
        # Memory consolidation log (tracks merged memories)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS consolidation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_ids TEXT NOT NULL,
                target_id TEXT NOT NULL,
                consolidated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                reason TEXT
            )
        ''')
        
        # Indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_memory_type ON memories(memory_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON memories(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_relevance ON memories(relevance_score DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_access_count ON memories(access_count DESC)')
        
        conn.commit()
        conn.close()
        logger.info("Memory database initialized")
    
    def store_memory(
        self,
        content: str,
        memory_type: MemoryType,
        tags: List[str] = None,
        metadata: Dict[str, Any] = None,
    ) -> MemoryEntry:
        """
        Store a new memory entry.
        
        Args:
            content: The memory content
            memory_type: Type of memory
            tags: Tags for categorization and search
            metadata: Additional metadata
            
        Returns:
            The created MemoryEntry
        """
        import uuid
        
        memory_id = str(uuid.uuid4())
        now = datetime.now()
        tags = tags or []
        metadata = metadata or {}
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO memories (id, content, memory_type, created_at, updated_at, tags, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            memory_id,
            content,
            memory_type.value,
            now.isoformat(),
            now.isoformat(),
            json.dumps(tags),
            json.dumps(metadata),
        ))
        
        conn.commit()
        conn.close()
        
        entry = MemoryEntry(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            created_at=now,
            updated_at=now,
            tags=tags,
            metadata=metadata,
        )
        
        self._memory_cache[memory_id] = entry
        logger.info(f"Stored memory: {memory_id} ({memory_type.value})")
        
        return entry
    
    def search_memories(
        self,
        query: str,
        memory_type: MemoryType = None,
        tags: List[str] = None,
        limit: int = 10,
        min_relevance: float = 0.3,
    ) -> List[MemoryEntry]:
        """
        Search for relevant memories using keyword and tag matching.
        
        Args:
            query: Search query
            memory_type: Filter by memory type
            tags: Filter by tags (AND operation)
            limit: Maximum results
            min_relevance: Minimum relevance threshold
            
        Returns:
            List of matching memories sorted by relevance
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        sql = 'SELECT * FROM memories WHERE 1=1'
        params = []
        
        # Add query matching (simple substring for now, can be enhanced with FTS)
        sql += ' AND (content LIKE ? OR tags LIKE ?)'
        params.extend([f'%{query}%', f'%{query}%'])
        
        # Filter by memory type
        if memory_type:
            sql += ' AND memory_type = ?'
            params.append(memory_type.value)
        
        # Filter by relevance
        sql += ' AND relevance_score >= ?'
        params.append(min_relevance)
        
        # Order by relevance and recency
        sql += ' ORDER BY relevance_score DESC, updated_at DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            memory = self._row_to_memory(row)
            results.append(memory)
            # Update access stats
            self._update_access_stats(memory.id)
        
        logger.info(f"Search found {len(results)} memories for query: '{query}'")
        return results
    
    def get_context_memories(self, num_recent: int = 5) -> List[MemoryEntry]:
        """Get the most recent context memories (conversation history)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM memories
            WHERE memory_type = ?
            ORDER BY updated_at DESC
            LIMIT ?
        ''', (MemoryType.CONTEXT.value, num_recent))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_memory(row) for row in rows]
    
    def link_memories(
        self,
        from_id: str,
        to_id: str,
        relationship_type: str,
        confidence: float = 1.0,
    ):
        """
        Create a relationship link between two memories (knowledge graph).
        
        Args:
            from_id: Source memory ID
            to_id: Target memory ID
            relationship_type: Type of relationship (e.g., "related_to", "caused_by")
            confidence: Confidence level (0-1)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO memory_relationships
                (from_id, to_id, relationship_type, confidence)
                VALUES (?, ?, ?, ?)
            ''', (from_id, to_id, relationship_type, confidence))
            
            conn.commit()
            logger.info(f"Linked memories: {from_id} --{relationship_type}--> {to_id}")
        except Exception as e:
            logger.error(f"Failed to link memories: {e}")
        finally:
            conn.close()
    
    def get_related_memories(self, memory_id: str) -> List[Tuple[str, MemoryEntry]]:
        """Get all memories related to a given memory."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get both forward and backward relationships
        cursor.execute('''
            SELECT DISTINCT to_id FROM memory_relationships WHERE from_id = ?
            UNION
            SELECT DISTINCT from_id FROM memory_relationships WHERE to_id = ?
        ''', (memory_id, memory_id))
        
        related_ids = [row[0] for row in cursor.fetchall()]
        
        if not related_ids:
            conn.close()
            return []
        
        placeholders = ','.join('?' * len(related_ids))
        cursor.execute(f'SELECT * FROM memories WHERE id IN ({placeholders})', related_ids)
        rows = cursor.fetchall()
        conn.close()
        
        return [(row[1], self._row_to_memory(row)) for row in rows]
    
    def consolidate_memories(self, memory_ids: List[str], reason: str = "automatic"):
        """
        Merge multiple related memories into a consolidated entry.
        Useful for reducing memory clutter and improving search efficiency.
        """
        if len(memory_ids) < 2:
            return None
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Fetch all memories to consolidate
        placeholders = ','.join('?' * len(memory_ids))
        cursor.execute(f'SELECT * FROM memories WHERE id IN ({placeholders})', memory_ids)
        rows = cursor.fetchall()
        
        if not rows:
            conn.close()
            return None
        
        # Merge content (sort by date)
        memories = [self._row_to_memory(row) for row in rows]
        memories.sort(key=lambda m: m.created_at)
        
        merged_content = " | ".join([m.content for m in memories])
        merged_tags = list(set([tag for m in memories for tag in (m.tags or [])]))
        merged_metadata = {}
        for m in memories:
            merged_metadata.update(m.metadata or {})
        
        # Create consolidated entry
        consolidated = self.store_memory(
            content=merged_content,
            memory_type=memories[0].memory_type,
            tags=merged_tags,
            metadata={**merged_metadata, "consolidated_from": memory_ids},
        )
        
        # Log consolidation
        cursor.execute('''
            INSERT INTO consolidation_log (source_ids, target_id, reason)
            VALUES (?, ?, ?)
        ''', (json.dumps(memory_ids), consolidated.id, reason))
        
        # Delete old memories (optional - can archive instead)
        for mid in memory_ids:
            cursor.execute('DELETE FROM memories WHERE id = ?', (mid,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Consolidated {len(memory_ids)} memories into {consolidated.id}")
        return consolidated
    
    def decay_memory_relevance(self, days_old: int = 30):
        """
        Gradually reduce relevance of older memories.
        Called periodically to prioritize recent memories.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
        
        # Reduce relevance for old memories (multiplicative decay)
        cursor.execute('''
            UPDATE memories
            SET relevance_score = relevance_score * 0.9
            WHERE created_at < ? AND relevance_score > 0.1
        ''', (cutoff_date,))
        
        conn.commit()
        conn.close()
        logger.info(f"Applied memory decay to entries older than {days_old} days")
    
    def _row_to_memory(self, row: tuple) -> MemoryEntry:
        """Convert database row to MemoryEntry object."""
        return MemoryEntry(
            id=row[0],
            content=row[1],
            memory_type=MemoryType(row[2]),
            created_at=datetime.fromisoformat(row[3]),
            updated_at=datetime.fromisoformat(row[4]),
            relevance_score=row[5],
            tags=json.loads(row[6]) if row[6] else [],
            metadata=json.loads(row[7]) if row[7] else {},
        )
    
    def _update_access_stats(self, memory_id: str):
        """Update access statistics for a memory."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE memories
            SET access_count = access_count + 1,
                last_accessed = ?,
                relevance_score = MIN(2.0, relevance_score * 1.05)
            WHERE id = ?
        ''', (datetime.now().isoformat(), memory_id))
        
        conn.commit()
        conn.close()
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get statistics about the memory system."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM memories')
        total_memories = cursor.fetchone()[0]
        
        cursor.execute('SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type')
        by_type = dict(cursor.fetchall())
        
        cursor.execute('SELECT AVG(relevance_score) FROM memories')
        avg_relevance = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(access_count) FROM memories')
        total_accesses = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            "total_memories": total_memories,
            "by_type": by_type,
            "average_relevance": round(avg_relevance, 2),
            "total_accesses": total_accesses,
            "cache_size": len(self._memory_cache),
        }


# Global instance
_memory_manager = None


def get_memory_manager() -> EnhancedMemoryManager:
    """Get or create the global memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = EnhancedMemoryManager()
    return _memory_manager
