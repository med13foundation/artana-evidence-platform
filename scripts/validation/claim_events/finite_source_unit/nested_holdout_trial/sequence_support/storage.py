"""Canonical hashing and atomic JSON replacement for repeat registries."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode(),
    ).hexdigest()


def replace_json(path: Path, value: Mapping[str, object]) -> None:
    replacement = path.with_suffix(f"{path.suffix}.tmp")
    replacement.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    replacement.replace(path)


__all__ = ["canonical_sha256", "replace_json"]
