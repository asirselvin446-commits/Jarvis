"""
Tests for the process-wide MemoryManager singleton accessor.

Before this, plugins/memory_tools built a fresh MemoryManager() on every
tool call (new SQLite connection + ChromaDB client each time) while the
orchestrator held a separate instance. get_memory_manager() gives everyone
one shared instance.
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.memory as memory_mod


class TestSingletonAccessor:
    def setup_method(self):
        # Start each test from a clean singleton slot.
        memory_mod._memory_manager_instance = None

    def teardown_method(self):
        inst = memory_mod._memory_manager_instance
        if inst is not None:
            try:
                inst.close()
            except Exception:
                pass
        memory_mod._memory_manager_instance = None

    def test_returns_same_instance(self, temp_dir, monkeypatch):
        monkeypatch.setattr("core.memory.SQLITE_DB", os.path.join(temp_dir, "s.db"))
        monkeypatch.setattr("core.memory.CHROMA_DIR", os.path.join(temp_dir, "chroma"))
        a = memory_mod.get_memory_manager()
        b = memory_mod.get_memory_manager()
        assert a is b

    def test_memory_tools_uses_singleton(self, temp_dir, monkeypatch):
        monkeypatch.setattr("core.memory.SQLITE_DB", os.path.join(temp_dir, "s.db"))
        monkeypatch.setattr("core.memory.CHROMA_DIR", os.path.join(temp_dir, "chroma"))
        import plugins.memory_tools as mt
        assert mt._get_memory() is memory_mod.get_memory_manager()

    def test_thread_safe_single_construction(self, temp_dir, monkeypatch):
        """Concurrent first-callers must all get the exact same instance."""
        monkeypatch.setattr("core.memory.SQLITE_DB", os.path.join(temp_dir, "s.db"))
        monkeypatch.setattr("core.memory.CHROMA_DIR", os.path.join(temp_dir, "chroma"))

        results = []
        barrier = threading.Barrier(8)

        def grab():
            barrier.wait()
            results.append(memory_mod.get_memory_manager())

        threads = [threading.Thread(target=grab) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == 8
        assert all(r is results[0] for r in results)

    def test_shared_data_across_callers(self, temp_dir, monkeypatch):
        """A preference set via one handle is visible via another."""
        monkeypatch.setattr("core.memory.SQLITE_DB", os.path.join(temp_dir, "s.db"))
        monkeypatch.setattr("core.memory.CHROMA_DIR", os.path.join(temp_dir, "chroma"))
        memory_mod.get_memory_manager().set_preference("wake_word", "jarvis")
        assert memory_mod.get_memory_manager().get_preference("wake_word") == "jarvis"
