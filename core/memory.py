"""
J.A.R.V.I.S. Memory Manager
Handles structured memory (SQLite) and semantic memory (ChromaDB).
Supports: Conversation Memory, Project Memory, Preference Memory, Task Memory, Learning Memory.
"""

import os
import sqlite3
import threading
import logging
import chromadb
from datetime import datetime

logger = logging.getLogger("jarvis.memory")

# Maximum entries in ChromaDB collections before pruning
MAX_CONVERSATION_ENTRIES = 1000
MAX_LEARNING_ENTRIES = 500

# Initialize database paths
DB_DIR = os.path.join(os.path.expanduser("~"), ".jarvis", "memory")
os.makedirs(DB_DIR, exist_ok=True)
SQLITE_DB = os.path.join(DB_DIR, "jarvis_memory.sqlite")
CHROMA_DIR = os.path.join(DB_DIR, "chroma_db")
USER_MD = os.path.join(DB_DIR, "USER.md")
MEMORY_MD = os.path.join(DB_DIR, "MEMORY.md")


class MemoryManager:
    def __init__(self):
        self._db_lock = threading.Lock()
        self._init_sqlite()
        self._init_chroma()
        self._init_markdown()

    def _init_markdown(self):
        """Ensure durable Markdown memory files exist."""
        if not os.path.exists(USER_MD):
            with open(USER_MD, "w", encoding="utf-8") as f:
                f.write("# User Identity & Preferences\n\n- User is the creator and master of this system.\n")
        if not os.path.exists(MEMORY_MD):
            with open(MEMORY_MD, "w", encoding="utf-8") as f:
                f.write("# Durable Memory (Curated by Dreaming Daemon)\n\n")

    def _init_sqlite(self):
        """Initialize SQLite database for structured data."""
        self.conn = sqlite3.connect(SQLITE_DB, check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # Enable WAL mode for safe concurrent reads/writes from multiple threads
        self.conn.execute("PRAGMA journal_mode=WAL")
        # Wait up to 5 seconds if another thread holds the lock
        self.conn.execute("PRAGMA busy_timeout=5000")
        
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
        
        # Knowledge Graph (Triplets) Table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS triplets (
                subject TEXT,
                predicate TEXT,
                object TEXT,
                timestamp DATETIME,
                PRIMARY KEY (subject, predicate, object)
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
        self.voice_memory = self.chroma_client.get_or_create_collection(name="voice_patterns")
        self.document_memory = self.chroma_client.get_or_create_collection(name="documents")

        # In-memory command frequency tracker (persisted to SQLite)
        self.command_frequency: dict[str, int] = {}
        self._load_command_frequency()

    # ─── Structured Memory (SQLite) ─────────────────────────────────

    def set_preference(self, key: str, value: str):
        """Save a user preference."""
        now = datetime.now().isoformat()
        with self._db_lock:
            self.cursor.execute('''
                INSERT INTO preferences (key, value, updated_at) 
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            ''', (key, value, now))
            self.conn.commit()

    def get_preference(self, key: str) -> str | None:
        """Retrieve a user preference."""
        with self._db_lock:
            self.cursor.execute('SELECT value FROM preferences WHERE key = ?', (key,))
            row = self.cursor.fetchone()
        return row[0] if row else None

    def add_task(self, description: str):
        """Add a task to memory."""
        now = datetime.now().isoformat()
        with self._db_lock:
            self.cursor.execute('INSERT INTO tasks (description, status, created_at) VALUES (?, ?, ?)',
                                (description, 'pending', now))
            self.conn.commit()

    def get_pending_tasks(self) -> list:
        """Get all pending tasks."""
        with self._db_lock:
            self.cursor.execute('SELECT id, description, created_at FROM tasks WHERE status = "pending"')
            return [{"id": row[0], "description": row[1], "created_at": row[2]} for row in self.cursor.fetchall()]

    # ─── Graph Memory (Knowledge Graph) ──────────────────────────────

    def add_triplet(self, subject: str, predicate: str, obj: str):
        """Add an Entity-Relationship-Entity triplet to the Knowledge Graph."""
        now = datetime.now().isoformat()
        try:
            with self._db_lock:
                self.cursor.execute('''
                    INSERT INTO triplets (subject, predicate, object, timestamp)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(subject, predicate, object) DO UPDATE SET timestamp=excluded.timestamp
                ''', (subject.lower(), predicate.lower(), obj.lower(), now))
                self.conn.commit()
        except Exception:
            pass

    def get_triplets(self, entity: str) -> list:
        """Get all triplets involving the given entity (either as subject or object)."""
        entity = entity.lower()
        with self._db_lock:
            self.cursor.execute('''
                SELECT subject, predicate, object FROM triplets 
                WHERE subject = ? OR object = ?
            ''', (entity, entity))
            return [{"subject": row[0], "predicate": row[1], "object": row[2]} for row in self.cursor.fetchall()]

    def get_relevant_triplets(self, text: str) -> list:
        """Find any facts in the knowledge graph where the subject or object appears in the text."""
        text_lower = text.lower()
        with self._db_lock:
            self.cursor.execute('SELECT subject, predicate, object FROM triplets')
            all_triplets = self.cursor.fetchall()
        
        relevant = []
        for row in all_triplets:
            subj, pred, obj = row
            if subj in text_lower or obj in text_lower:
                relevant.append({"subject": subj, "predicate": pred, "object": obj})

        return relevant

    def get_all_triplets_summary(self, max_entries: int = 50) -> str:
        """
        Return a compact, readable summary of ALL known facts in the knowledge graph.
        Injected into every LLM call so Jarvis always knows everything about the user.
        """
        with self._db_lock:
            self.cursor.execute(
                'SELECT subject, predicate, object FROM triplets ORDER BY timestamp DESC LIMIT ?',
                (max_entries,)
            )
            rows = self.cursor.fetchall()

        if not rows:
            return ""

        facts = []
        for s, p, o in rows:
            readable = f"- {s} {p.replace('_', ' ')}: {o}"
            facts.append(readable)

        return "\n".join(facts)

    def get_triplet_count(self) -> int:
        """Return the number of facts in the knowledge graph."""
        with self._db_lock:
            self.cursor.execute('SELECT COUNT(*) FROM triplets')
            return self.cursor.fetchone()[0]

    # ─── Durable Memory (Markdown) ──────────────────────────────────
    
    def get_core_identity(self) -> str:
        """Reads USER.md for core identity and preferences."""
        try:
            with open(USER_MD, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error("Failed to read USER.md: %s", e)
            return ""

    def get_durable_memory(self) -> str:
        """Reads MEMORY.md for long-term curated facts."""
        try:
            with open(MEMORY_MD, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error("Failed to read MEMORY.md: %s", e)
            return ""

    def append_durable_memory(self, fact: str):
        """Appends a new curated fact to MEMORY.md."""
        try:
            with open(MEMORY_MD, "a", encoding="utf-8") as f:
                f.write(f"- {fact}\n")
        except Exception as e:
            logger.error("Failed to write to MEMORY.md: %s", e)

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

    # ─── Voice Memory ───────────────────────────────────────────────

    def add_voice_pattern(self, raw_speech: str, resolved_command: str):
        """Learn that a particular speech pattern maps to a command."""
        now = datetime.now().isoformat()
        doc_id = f"voice_{now}"
        self.voice_memory.add(
            documents=[f"{raw_speech} → {resolved_command}"],
            metadatas=[{"raw": raw_speech, "resolved": resolved_command, "timestamp": now}],
            ids=[doc_id]
        )

    def find_similar_voice_pattern(self, speech: str) -> str | None:
        """Find a previously learned voice pattern similar to this speech."""
        if self.voice_memory.count() == 0:
            return None
        results = self.voice_memory.query(
            query_texts=[speech],
            n_results=1
        )
        if results and results["documents"] and results["documents"][0]:
            meta = results["metadatas"][0][0]
            return meta.get("resolved")
        return None

    def add_nickname(self, nickname: str, resolved_name: str, category: str = "general"):
        """Store a user nickname: 'code' → 'Visual Studio Code'."""
        self.set_preference(f"nickname_{category}_{nickname}", resolved_name)

    def get_nickname(self, nickname: str, category: str = "general") -> str | None:
        """Retrieve a stored nickname."""
        return self.get_preference(f"nickname_{category}_{nickname}")

    def record_command(self, command: str):
        """Track command frequency for prediction."""
        normalized = command.strip().lower()
        self.command_frequency[normalized] = self.command_frequency.get(normalized, 0) + 1
        # Persist to SQLite periodically
        self._save_command_frequency()

    def get_frequent_commands(self, n: int = 10) -> list:
        """Return the N most frequently used commands."""
        sorted_cmds = sorted(self.command_frequency.items(), key=lambda x: x[1], reverse=True)
        return [{"command": cmd, "count": count} for cmd, count in sorted_cmds[:n]]

    def _load_command_frequency(self):
        """Load command frequency data from SQLite."""
        try:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS command_frequency (
                    command TEXT PRIMARY KEY,
                    count INTEGER DEFAULT 0,
                    last_used DATETIME
                )
            ''')
            self.conn.commit()

            self.cursor.execute('SELECT command, count FROM command_frequency')
            for row in self.cursor.fetchall():
                self.command_frequency[row[0]] = row[1]
        except Exception:
            pass

    def _save_command_frequency(self):
        """Persist command frequency data to SQLite."""
        try:
            now = datetime.now().isoformat()
            with self._db_lock:
                for cmd, count in self.command_frequency.items():
                    self.cursor.execute('''
                        INSERT INTO command_frequency (command, count, last_used)
                        VALUES (?, ?, ?)
                        ON CONFLICT(command) DO UPDATE SET count=excluded.count, last_used=excluded.last_used
                    ''', (cmd, count, now))
                self.conn.commit()
        except Exception:
            pass

    # ─── Memory Pruning ──────────────────────────────────────────────

    def _prune_collection(self, collection, max_entries: int):
        """Prune a ChromaDB collection to keep only the most recent entries."""
        try:
            count = collection.count()
            if count <= max_entries:
                return
            
            # Get all IDs sorted by metadata timestamp, delete the oldest
            excess = count - max_entries
            results = collection.get(
                limit=excess,
                include=["metadatas"]
            )
            if results and results["ids"]:
                collection.delete(ids=results["ids"])
                logger.info("Pruned %d entries from collection (was %d, max %d)",
                           len(results["ids"]), count, max_entries)
        except Exception as e:
            logger.debug("Collection pruning error: %s", e)

    def prune_all(self):
        """Prune all collections to prevent unbounded growth."""
        self._prune_collection(self.conversation_memory, MAX_CONVERSATION_ENTRIES)
        self._prune_collection(self.learning_memory, MAX_LEARNING_ENTRIES)

    # ─── Lifecycle ───────────────────────────────────────────────────

    def close(self):
        """Cleanly close all database connections. Call on shutdown."""
        try:
            self._save_command_frequency()
            self.prune_all()
        except Exception:
            pass
        
        try:
            with self._db_lock:
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self.conn.close()
            logger.info("SQLite connection closed cleanly.")
        except Exception as e:
            logger.error("Error closing SQLite: %s", e)


# ─── Singleton accessor ──────────────────────────────────────────

_memory_manager_instance: "MemoryManager | None" = None
_memory_manager_lock = threading.Lock()


def get_memory_manager() -> "MemoryManager":
    """Return the process-wide MemoryManager, creating it once.

    Every caller must share one instance. Each MemoryManager opens its own
    SQLite connection and ChromaDB PersistentClient, so constructing them
    per-call — as plugins/memory_tools did on *every* tool invocation —
    leaks handles and risks ChromaDB conflicts on the same path. Mirrors the
    get_message_bus / get_control_plane singleton pattern used elsewhere.
    """
    global _memory_manager_instance
    if _memory_manager_instance is None:
        with _memory_manager_lock:
            if _memory_manager_instance is None:
                _memory_manager_instance = MemoryManager()
    return _memory_manager_instance

