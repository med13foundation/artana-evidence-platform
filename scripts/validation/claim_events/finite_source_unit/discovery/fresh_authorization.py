"""Authorization boundary for the first post-#176 fresh scientific unit."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

_REPO_ROOT: Final = Path(__file__).resolve().parents[5]
_PR176_REPORT_PATH: Final = (
    _REPO_ROOT / "docs/validation/reports/2026-07-18-tg04-transport-identity-smoke.md"
)
_PR176_REPORT_SHA256: Final = (
    "61b5ca507a26b6cfe20f02c28b29b71ac09ffcff2a58c056d149a18286823978"
)


def verify_fresh_discovery_authorization(
    path: Path = _PR176_REPORT_PATH,
    *,
    expected_sha256: str = _PR176_REPORT_SHA256,
) -> str:
    """Pin the merged #176 report that authorizes one fresh source unit."""

    report_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if report_sha256 != expected_sha256:
        raise RuntimeError("#176 transport-identity report changed")
    return report_sha256


__all__ = ["verify_fresh_discovery_authorization"]
