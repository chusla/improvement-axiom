"""Files on disk: atomic JSON writes and the run directory layout.

runs/<run>/manifest.json                     config snapshot, prompt hashes, commits
runs/<run>/conversations/<conv_id>.json      one conversation, saved after every message
runs/<run>/judgements/<judge>/<conv_id>.json per-turn judgements from one judge
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=1)
        # Windows: antivirus or the indexer can hold the target for a moment; retry instead of failing the run.
        for attempt in range(20):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05 * (attempt + 1))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RunDir:
    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    def conversation(self, conv_id: str) -> Path:
        return self.root / "conversations" / f"{conv_id}.json"

    def judgement(self, judge_key: str, conv_id: str) -> Path:
        return self.root / "judgements" / judge_key / f"{conv_id}.json"

    def conversations(self) -> list[Path]:
        d = self.root / "conversations"
        return sorted(d.glob("*.json")) if d.exists() else []

    def judgements(self, judge_key: str) -> list[Path]:
        d = self.root / "judgements" / judge_key
        return sorted(d.glob("*.json")) if d.exists() else []
