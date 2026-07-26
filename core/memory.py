"""
J.A.R.V.I.S. Memory Manager
Handles structured memory (SQLite) and semantic memory (ChromaDB).
Supports: Conversation Memory, Project Memory, Preference Memory, Task Memory, Learning Memory.
"""

import os
import sqlite3
import chromadb
from datetime import datetime

# Initialize database paths
DB_DIR = os.path.join(os.path.expanduser("~"), ".jarvis", "memory")
os.makedirs(DB_DIR, exist_ok=True)
SQLITE_DB = os.path.join(DB_DIR, "jarvis_memory.sqlite")
CHROMA_DIR = os.path.join(DB_DIR, "chroma_db")


class MemoryManager:
    def __init__(self):
        self._init_sqlite()
        self._init_chroma()

    def _init_sqlite(self):
        """Initialize SQLite database for structured data."""
        self.conn = sqlite3.connect(SQLITE_DB, check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # Preferences Table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at DATETIME
            )
        ''')
        
        # Tasks Table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT,
                status TEXT,
                created_at DATETIME,
                completed_at DATETIME
            )
        ''')
        self.conn.commit()

    def _init_chroma(self):
        """Initialize ChromaDB for semantic search."""
        # Using PersistentClient so memory survives restarts
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
        
        # Collections for different memory types
        self.conversation_memory = self.chroma_client.get_or_create_collection(name="conversation")
        self.learning_memory = self.chroma_client.get_or_create_collection(name="learning")
        self.project_memory = self.chroma_client.get_or_create_collection(name="project")

    # ─── Structured Memory (SQLite) ─────────────────────────────────

    def set_preference(self, key: str, value: str):
        """Save a user preference."""
        now = datetime.now().isoformat()
        self.cursor.execute('''
            INSERT INTO preferences (key, value, updated_at) 
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        ''', (key, value, now))
        self.conn.commit()

    def get_preference(self, key: str) -> str | None:
        """Retrieve a user preference."""
        self.cursor.execute('SELECT value FROM preferences WHERE key = ?', (key,))
        row = self.cursor.fetchone()
        return row[0] if row else None

    def add_task(self, description: str):
        """Add a task to memory."""
        now = datetime.now().isoformat()
        self.cursor.execute('INSERT INTO tasks (description, status, created_at) VALUES (?, ?, ?)',
                            (description, 'pending', now))
        self.conn.commit()

    def get_pending_tasks(self) -> list:
        """Get all pending tasks."""
        self.cursor.execute('SELECT id, description, created_at FROM tasks WHERE status = "pending"')
        return [{"id": row[0], "description": row[1], "created_at": row[2]} for row in self.cursor.fetchall()]

    # ─── Semantic Memory (ChromaDB) ─────────────────────────────────

    def add_conversation(self, role: str, text: str):
        """Store conversation history semantically."""
        now = datetime.now().isoformat()
        doc_id = f"msg_{now}_{role}"
        self.conversation_memory.add(
            documents=[text],
            metadatas=[{"role": role, "timestamp": now}],
            ids=[doc_id]
        )

    def retrieve_relevant_conversation(self, query: str, n_results: int = 3) -> list:
        """Find past conversation bits relevant to a query."""
        if self.conversation_memory.count() == 0:
            return []
            
        results = self.conversation_memory.query(
            query_texts=[query],
            n_results=min(n_results, self.conversation_memory.count())
        )
        
        memories = []
        if results and "documents" in results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i]
                memories.append(f"[{meta['timestamp']}] {meta['role']}: {doc}")
        return memories

    def add_learning(self, fact: str):
        """Store a permanent fact or learning."""
        now = datetime.now().isoformat()
        doc_id = f"fact_{now}"
        self.learning_memory.add(
            documents=[fact],
            metadatas=[{"timestamp": now}],
            ids=[doc_id]
        )

    def retrieve_relevant_learnings(self, query: str, n_results: int = 2) -> list:
        """Find relevant learned facts."""
        if self.learning_memory.count() == 0:
            return []
            
        results = self.learning_memory.query(
            query_texts=[query],
            n_results=min(n_results, self.learning_memory.count())
        )
        return results["documents"][0] if results and "documents" in results and results["documents"] else []
