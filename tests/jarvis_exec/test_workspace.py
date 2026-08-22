import os
from pathlib import Path

import pytest

from jarvis.exec.contract import MAX_FILES, MAX_TEXT_BYTES
from jarvis.exec import workspace as workspace_module
from jarvis.exec.workspace import Workspace, WorkspaceError


@pytest.fixture
def workspace(tmp_path: Path):
    value = Workspace(tmp_path / "workspace")
    yield value
    value.close()


def test_text_workspace_round_trip_and_list_delete(workspace: Workspace) -> None:
    assert workspace.write_text("site/index.html", "hello")["size"] == 5
    assert workspace.read_text("site/index.html")["text"] == "hello"
    assert workspace.list()["files"] == [{"path": "site/index.html", "size": 5}]
    assert workspace.delete("site/index.html")["ok"] is True
    assert workspace.list()["files"] == []


@pytest.mark.parametrize("path", ["", "/etc/passwd", "../secret", "a/../../secret", "a/./b", "bad\x00path"])
def test_rejects_invalid_paths(workspace: Workspace, path: str) -> None:
    with pytest.raises(WorkspaceError):
        workspace.write_text(path, "x")


def test_rejects_symlink_escape(workspace: Workspace, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, workspace.root / "escape")
    with pytest.raises((WorkspaceError, OSError)):
        workspace.write_text("escape/value", "x")
    assert not (outside / "value").exists()


def test_rejects_replaced_parent_symlink(workspace: Workspace, tmp_path: Path) -> None:
    workspace.write_text("parent/value", "old")
    (workspace.root / "parent/value").unlink()
    (workspace.root / "parent").rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, workspace.root / "parent")
    with pytest.raises(OSError):
        workspace.write_text("parent/value", "new")
    assert not (outside / "value").exists()


def test_enforces_file_and_count_limits(workspace: Workspace) -> None:
    with pytest.raises(WorkspaceError, match="file_too_large"):
        workspace.write_text("large", "x" * (MAX_TEXT_BYTES + 1))
    for index in range(MAX_FILES):
        workspace.write_text(f"f{index}", "x")
    with pytest.raises(WorkspaceError, match="file_count_limit"):
        workspace.write_text("overflow", "x")


def test_enforces_total_workspace_limit(workspace: Workspace, monkeypatch) -> None:
    monkeypatch.setattr(workspace_module, "WORKSPACE_BYTES", 8)
    workspace.write_text("full", "12345678")
    with pytest.raises(WorkspaceError, match="workspace_full"):
        workspace.write_text("overflow", "x")
