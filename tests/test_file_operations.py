"""
Tests for plugins.file_operations — find/open/move/copy/rename/delete.

Deletion is exercised against a fake recycler so the suite never touches
the real Recycle Bin; the guard rails around it are tested for real.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plugins.file_operations as fo


@pytest.fixture
def sandbox(tmp_path):
    """A temp folder with one file and an empty subfolder."""
    src = tmp_path / "jarvis_test_doc.txt"
    src.write_text("hello jarvis " * 20)
    sub = tmp_path / "sub"
    sub.mkdir()
    return tmp_path, src, sub


class TestProtectedPaths:
    def test_system_root_is_protected(self):
        assert fo._is_protected(os.path.join(os.environ["SystemRoot"], "System32")) is True

    def test_drive_root_is_protected(self):
        assert fo._is_protected("C:" + os.sep) is True

    def test_normal_file_not_protected(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x")
        assert fo._is_protected(str(f)) is False

    def test_delete_refuses_system_file(self, monkeypatch):
        called = []
        monkeypatch.setattr(fo, "_recycle", lambda p: called.append(p) or (True, ""))
        out = fo.delete_file(os.path.join(os.environ["SystemRoot"], "explorer.exe"))
        assert "Refused" in out
        assert called == []  # never even attempted

    def test_move_refuses_into_system(self, sandbox, monkeypatch):
        _, src, _ = sandbox
        monkeypatch.setattr(fo, "_resolve_location", lambda loc: os.environ["SystemRoot"])
        out = fo.move_file(str(src), "windows")
        assert "Refused" in out
        assert os.path.exists(src)  # original untouched


class TestFindAndList:
    def test_find_by_partial_name(self, sandbox):
        tmp, _, _ = sandbox
        out = fo.find_files("jarvis_test", str(tmp))
        assert "jarvis_test_doc.txt" in out

    def test_find_no_match(self, sandbox):
        tmp, _, _ = sandbox
        out = fo.find_files("nothing_like_this_xyz", str(tmp))
        assert "No files matching" in out

    def test_find_bad_location(self):
        out = fo.find_files("x", "C:\\definitely\\not\\a\\real\\folder")
        assert "couldn't find the folder" in out

    def test_list_files(self, sandbox):
        tmp, _, _ = sandbox
        out = fo.list_files(str(tmp))
        assert "jarvis_test_doc.txt" in out
        assert "1 folder(s)" in out


class TestCopyMoveRename:
    def test_copy_then_verify(self, sandbox):
        _, src, sub = sandbox
        out = fo.copy_file(str(src), str(sub))
        assert "Copied" in out
        assert (sub / "jarvis_test_doc.txt").exists()
        assert src.exists()  # original stays

    def test_copy_refuses_overwrite(self, sandbox):
        _, src, sub = sandbox
        fo.copy_file(str(src), str(sub))
        out = fo.copy_file(str(src), str(sub))
        assert "already exists" in out

    def test_move_removes_original(self, sandbox):
        tmp, src, sub = sandbox
        out = fo.move_file(str(src), str(sub))
        assert "Moved" in out
        assert not src.exists()
        assert (sub / "jarvis_test_doc.txt").exists()

    def test_rename(self, sandbox):
        tmp, src, _ = sandbox
        out = fo.rename_file(str(src), "renamed.txt")
        assert "Renamed" in out
        assert (tmp / "renamed.txt").exists()

    def test_rename_refuses_overwrite(self, sandbox):
        tmp, src, _ = sandbox
        (tmp / "taken.txt").write_text("x")
        out = fo.rename_file(str(src), "taken.txt")
        assert "already exists" in out


class TestResolveFile:
    def test_missing_file_message(self):
        path, err = fo._resolve_file("definitely_no_such_file_xyz123")
        assert path is None
        assert "couldn't find" in err

    def test_empty_input(self):
        path, err = fo._resolve_file("  ")
        assert path is None
        assert "No file" in err

    def test_ambiguous_match_lists_options(self, tmp_path, monkeypatch):
        (tmp_path / "report_a.txt").write_text("x")
        (tmp_path / "report_b.txt").write_text("x")
        monkeypatch.setattr(fo, "DIRECTORIES", {"desktop": str(tmp_path)})
        monkeypatch.setattr(fo, "_DEFAULT_SEARCH_DIRS", ["desktop"])
        path, err = fo._resolve_file("report")
        assert path is None
        assert "matches 2 files" in err


class TestDelete:
    def test_delete_uses_recycle_bin(self, sandbox, monkeypatch):
        """Delete must route through the recycler, never os.remove."""
        _, src, _ = sandbox
        recycled = []

        def fake_recycle(p):
            recycled.append(p)
            os.remove(p)
            return True, ""

        monkeypatch.setattr(fo, "_recycle", fake_recycle)
        out = fo.delete_file(str(src))
        assert recycled == [str(src)]
        assert "Recycle Bin" in out

    def test_delete_reports_failure_honestly(self, sandbox, monkeypatch):
        _, src, _ = sandbox
        monkeypatch.setattr(fo, "_recycle", lambda p: (False, "access denied"))
        out = fo.delete_file(str(src))
        assert "Failed to delete" in out
        assert src.exists()

    def test_delete_flagged_dangerous(self):
        from core.tool_manager import _TOOL_REGISTRY
        meta = _TOOL_REGISTRY["delete_file"]
        assert meta["is_dangerous"] is True
        assert meta["requires_confirmation"] is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Recycle Bin only")
class TestRealRecycleBin:
    """Exercises the real SHFileOperationW path on a throwaway temp file.

    The mocked delete tests above can't catch a malformed struct or a bad
    flag, which is exactly where this code would break.
    """

    def test_recycle_actually_removes_temp_file(self, tmp_path):
        victim = tmp_path / "jarvis_recycle_probe.txt"
        victim.write_text("temporary file created by the Jarvis test suite")

        ok, msg = fo._recycle(str(victim))

        assert ok is True, f"_recycle failed: {msg}"
        assert not victim.exists()
