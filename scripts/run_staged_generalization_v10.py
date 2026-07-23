#!/usr/bin/env python3
"""Verify the non-executed V10 occurrence-boundary preregistration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.public_gold.staged_event.generalization.repair_v10.config import (  # noqa: E402
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.exposed_audit import (  # noqa: E402
    audit,
    write_audit,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.preflight import (  # noqa: E402
    verify,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("verify", "audit"), default="verify", nargs="?"
    )
    args = parser.parse_args()
    if args.command == "verify":
        value = verify()
    else:
        verify()
        result = audit()
        write_audit(DEFAULT_PATHS.exposed_audit_result, result)
        value = result.model_dump(mode="json")
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
