import os
from pathlib import Path

from jarvis.exec.execution import execute_python


def test_python_success_and_workspace(tmp_path: Path) -> None:
    result = execute_python("from pathlib import Path; Path('result.txt').write_text('ok'); print(2 + 3)", tmp_path)
    assert result["status"] == "completed"
    assert result["stdout"].strip() == "5"
    assert (tmp_path / "result.txt").read_text() == "ok"


def test_python_failure_and_minimal_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_DATABASE_URL", "dummy-secret")
    result = execute_python(
        "import os,sys; print('JARVIS_DATABASE_URL' in os.environ); sys.exit(3)", tmp_path
    )
    assert result["status"] == "failed"
    assert result["exit_code"] == 3
    assert result["stdout"].strip() == "False"


def test_stdout_and_stderr_are_bounded(tmp_path: Path) -> None:
    result = execute_python("import sys; print('x'*70000); print('y'*40000, file=sys.stderr)", tmp_path)
    assert len(result["stdout"].encode()) < 66_000
    assert len(result["stderr"].encode()) < 34_000
    assert "truncated" in result["stdout"]
    assert "truncated" in result["stderr"]
