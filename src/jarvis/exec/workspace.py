"""Descriptor-relative disposable text workspace operations."""

from __future__ import annotations

import os
import stat
import threading
from pathlib import Path, PurePosixPath

from .contract import MAX_FILES, MAX_TEXT_BYTES, WORKSPACE_BYTES


class WorkspaceError(ValueError):
    """Product-safe workspace validation failure."""


def _parts(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise WorkspaceError("invalid_path")
    raw_parts = value.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise WorkspaceError("invalid_path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise WorkspaceError("invalid_path")
    return path.parts


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self._lock = threading.RLock()

    def close(self) -> None:
        if self._root_fd >= 0:
            os.close(self._root_fd)
            self._root_fd = -1

    def _parent(self, path: str, *, create: bool) -> tuple[int, str]:
        parts = _parts(path)
        current = os.dup(self._root_fd)
        try:
            for component in parts[:-1]:
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=current)
                    except FileExistsError:
                        pass
                nxt = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=current,
                )
                os.close(current)
                current = nxt
            return current, parts[-1]
        except BaseException:
            os.close(current)
            raise

    def _usage(self) -> tuple[int, int]:
        count = total = 0
        for base, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = [name for name in dirs if not Path(base, name).is_symlink()]
            for name in files:
                item = Path(base, name)
                try:
                    info = item.lstat()
                except FileNotFoundError:
                    continue
                if stat.S_ISREG(info.st_mode):
                    count += 1
                    total += info.st_size
        return count, total

    def write_text(self, path: str, text: str) -> dict[str, object]:
        with self._lock:
            return self._write_text(path, text)

    def _write_text(self, path: str, text: str) -> dict[str, object]:
        if not isinstance(text, str):
            raise WorkspaceError("invalid_text")
        data = text.encode("utf-8")
        if len(data) > MAX_TEXT_BYTES:
            raise WorkspaceError("file_too_large")
        count, total = self._usage()
        parent, name = self._parent(path, create=True)
        temporary = f".{name}.jarvis-{os.getpid()}"
        try:
            previous = 0
            try:
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    raise WorkspaceError("invalid_path")
                previous = info.st_size
            except FileNotFoundError:
                if count >= MAX_FILES:
                    raise WorkspaceError("file_count_limit")
            if total - previous + len(data) > WORKSPACE_BYTES:
                raise WorkspaceError("workspace_full")
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=parent,
            )
            try:
                view = memoryview(data)
                while view:
                    written = os.write(fd, view)
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
            return {"ok": True, "path": path, "size": len(data)}
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
            os.close(parent)

    def read_text(self, path: str) -> dict[str, object]:
        with self._lock:
            return self._read_text(path)

    def _read_text(self, path: str) -> dict[str, object]:
        parent, name = self._parent(path, create=False)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_TEXT_BYTES:
                    raise WorkspaceError("invalid_file")
                data = os.read(fd, MAX_TEXT_BYTES + 1)
            finally:
                os.close(fd)
        except FileNotFoundError as error:
            raise WorkspaceError("not_found") from error
        finally:
            os.close(parent)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise WorkspaceError("not_text") from error
        return {"ok": True, "path": path, "text": text, "size": len(data)}

    def delete(self, path: str) -> dict[str, object]:
        with self._lock:
            return self._delete(path)

    def _delete(self, path: str) -> dict[str, object]:
        parent, name = self._parent(path, create=False)
        try:
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise WorkspaceError("invalid_file")
            os.unlink(name, dir_fd=parent)
        except FileNotFoundError as error:
            raise WorkspaceError("not_found") from error
        finally:
            os.close(parent)
        return {"ok": True, "path": path}

    def list(self) -> dict[str, object]:
        with self._lock:
            return self._list()

    def _list(self) -> dict[str, object]:
        entries: list[dict[str, object]] = []
        for base, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(name for name in dirs if not Path(base, name).is_symlink())
            for name in sorted(files):
                item = Path(base, name)
                info = item.lstat()
                if stat.S_ISREG(info.st_mode):
                    entries.append({"path": item.relative_to(self.root).as_posix(), "size": info.st_size})
        return {"ok": True, "files": entries[:MAX_FILES]}
