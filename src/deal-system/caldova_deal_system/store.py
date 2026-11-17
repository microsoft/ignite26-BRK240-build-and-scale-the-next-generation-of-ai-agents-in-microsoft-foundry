"""JSON file state with reset-to-seed. Single process; every write replaces the file atomically.

The seed is loaded on first start (no state file yet) or on an explicit reset."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def atomic_write_text(path: Path, text: str) -> None:
    """Write a temp file next to `path`, then os.replace it, so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class JsonStore:
    def __init__(self, state_dir: Path, seed_path: Path, *, reset: bool = False) -> None:
        self.state_dir = Path(state_dir)
        self.seed_path = Path(seed_path)
        self.path = self.state_dir / "deal_state.json"
        self._lock = threading.RLock()
        self._state: dict[str, Any] = {}
        if reset or not self.path.exists():
            self.reset()
        else:
            self._state = json.loads(self.path.read_text(encoding="utf-8"))

    def reset(self) -> dict[str, Any]:
        if not self.seed_path.exists():
            raise FileNotFoundError(f"Deal System seed not found: {self.seed_path} (run data/generate.py or set DEAL_SYSTEM_SEED_PATH)")
        seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        deals = {}
        for d in seed["deals"]:
            rec = copy.deepcopy(d)
            rec.update({
                "status": "open",
                "decisions": [],
                "approval_ids": [],
                "crm_activity": [],
                "approved_terms": None,
                "approved_terms_hash": None,
                "approved_by": None,
                "approved_at": None,
                "counter_terms": None,
                "term_sheet": None,
            })
            deals[rec["deal_id"]] = rec
        with self._lock:
            state = {"synthetic": True, "seed_generated_at": seed.get("generated_at"), "deals": deals, "approvals": {}, "inbox": []}
            self._flush(state)
            self._state = state
        for f in (self.state_dir / "term_sheets").glob("*.docx"):
            f.unlink()
        return {"deals": len(deals)}

    def read(self, fn: Callable[[dict[str, Any]], T]) -> T:
        with self._lock:
            return copy.deepcopy(fn(self._state))

    def mutate(self, fn: Callable[[dict[str, Any]], T]) -> T:
        """Apply fn to a copy; if it raises, neither memory nor disk changes."""
        with self._lock:
            working = copy.deepcopy(self._state)
            result = fn(working)
            self._flush(working)
            self._state = working
            return copy.deepcopy(result)

    def _flush(self, state: dict[str, Any]) -> None:
        atomic_write_text(self.path, json.dumps(state, indent=1))
