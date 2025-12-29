from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Tuple, TypeVar

from filelock import FileLock

T = TypeVar("T")


def _fresh_default_data() -> Dict[str, Any]:
    return {"users": [], "groups": [], "accounts": []}


def _normalize_data(data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    changed = False
    for key in ("users", "groups", "accounts"):
        value = data.get(key)
        if value is None or not isinstance(value, list):
            data[key] = []
            changed = True
    return data, changed


class JSONStore:
    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        lock_path = self.file_path.with_suffix(self.file_path.suffix + ".lock")
        self._file_lock = FileLock(str(lock_path))
        self._thread_lock = threading.RLock()

    def ensure_initialized(self) -> None:
        with self._thread_lock:
            self._ensure_parent_dir()
            with self._file_lock:
                if not self.file_path.exists() or self.file_path.stat().st_size == 0:
                    self._atomic_write_locked(_fresh_default_data())
                    return

                data = self._read_no_lock()
                data, changed = _normalize_data(data)
                if changed:
                    self._atomic_write_locked(data)

    def read(self) -> Dict[str, Any]:
        with self._thread_lock:
            self._ensure_parent_dir()
            with self._file_lock:
                if not self.file_path.exists() or self.file_path.stat().st_size == 0:
                    data = _fresh_default_data()
                    self._atomic_write_locked(data)
                    return data

                data = self._read_no_lock()
                data, changed = _normalize_data(data)
                if changed:
                    self._atomic_write_locked(data)
                return data

    def write(self, data: Dict[str, Any]) -> None:
        with self._thread_lock:
            self._ensure_parent_dir()
            with self._file_lock:
                self._atomic_write_locked(data)

    def update(self, mutator: Callable[[Dict[str, Any]], T]) -> T:
        with self._thread_lock:
            self._ensure_parent_dir()
            with self._file_lock:
                if not self.file_path.exists() or self.file_path.stat().st_size == 0:
                    self._atomic_write_locked(_fresh_default_data())

                data = self._read_no_lock()
                data, changed = _normalize_data(data)
                if changed:
                    self._atomic_write_locked(data)

                result = mutator(data)
                self._atomic_write_locked(data)
                return result

    def _ensure_parent_dir(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def _read_no_lock(self) -> Dict[str, Any]:
        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {self.file_path}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"{self.file_path} must contain a JSON object at the root")
        return data

    def _atomic_write_locked(self, data: Dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        tmp_dir = str(self.file_path.parent)
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=self.file_path.name + ".",
            suffix=".tmp",
            dir=tmp_dir,
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.file_path)
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
