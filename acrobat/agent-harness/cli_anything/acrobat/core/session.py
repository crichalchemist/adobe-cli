"""Stateful session management for cli-anything-acrobat.

The session tracks the currently open PDF project as a JSON file.
Uses exclusive file locking on save to prevent concurrent write corruption.
"""

from __future__ import annotations

import fcntl
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AcrobatSession:
    """In-memory session state for one PDF work session."""

    source_pdf: str = ""
    output_pdf: str = ""
    dirty: bool = False
    operations: list[dict] = field(default_factory=list)
    metadata_overrides: dict[str, str] = field(default_factory=dict)

    @property
    def has_project(self) -> bool:
        return bool(self.source_pdf)

    def log_operation(self, op_name: str, **details: Any) -> None:
        self.operations.append({"op": op_name, **details})
        self.dirty = True

    def to_dict(self) -> dict:
        return {
            "source_pdf": self.source_pdf,
            "output_pdf": self.output_pdf,
            "dirty": self.dirty,
            "operations": self.operations,
            "metadata_overrides": self.metadata_overrides,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AcrobatSession":
        sess = cls()
        sess.source_pdf = data.get("source_pdf", "")
        sess.output_pdf = data.get("output_pdf", "")
        sess.dirty = data.get("dirty", False)
        sess.operations = data.get("operations", [])
        sess.metadata_overrides = data.get("metadata_overrides", {})
        return sess


_SESSION: AcrobatSession | None = None


def get_session() -> AcrobatSession:
    global _SESSION
    if _SESSION is None:
        _SESSION = AcrobatSession()
    return _SESSION


def reset_session() -> None:
    global _SESSION
    _SESSION = AcrobatSession()


def _locked_save_json(path: str, data: dict) -> None:
    """Atomically write JSON with exclusive file locking."""
    try:
        f = open(path, "r+")
    except FileNotFoundError:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        f = open(path, "w")
    with f:
        locked = False
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            locked = True
        except (ImportError, OSError):
            pass
        try:
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=2)
            f.flush()
        finally:
            if locked:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def save_session(session_path: str) -> None:
    """Persist the current session to a JSON file."""
    sess = get_session()
    _locked_save_json(session_path, sess.to_dict())
    sess.dirty = False


def load_session(session_path: str) -> AcrobatSession:
    """Load session state from a JSON file."""
    global _SESSION
    with open(session_path) as f:
        data = json.load(f)
    _SESSION = AcrobatSession.from_dict(data)
    return _SESSION


def new_session(source_pdf: str, output_pdf: str | None = None) -> AcrobatSession:
    """Initialize a new session for the given PDF."""
    global _SESSION
    abs_src = str(Path(source_pdf).resolve())
    abs_out = output_pdf or abs_src
    _SESSION = AcrobatSession(source_pdf=abs_src, output_pdf=abs_out)
    return _SESSION
