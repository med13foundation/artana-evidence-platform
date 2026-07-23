#!/usr/bin/env python3
"""Preregister, verify, or execute the V13 exposed gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _local_root in (_REPO_ROOT, _SERVICES_ROOT):
    _local_root_text = str(_local_root)
    if _local_root_text in sys.path:
        sys.path.remove(_local_root_text)
    sys.path.insert(0, _local_root_text)

from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (  # noqa: E402
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.preflight import (  # noqa: E402
    verify,
    write_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.runner import (  # noqa: E402
    execute,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("preregister", "verify", "execute"),
    )
    args = parser.parse_args()
    if args.action == "preregister":
        write_candidate(DEFAULT_PATHS)
        result = verify(DEFAULT_PATHS)
        status = "V13_EXPOSED_GATE_PREREGISTERED"
    elif args.action == "verify":
        result = verify(DEFAULT_PATHS, remote_gate=True)
        status = "V13_EXPOSED_GATE_PREFLIGHT_PASS"
    else:
        print(execute())
        return 0
    print(
        json.dumps(
            {
                "status": status,
                "experiment_id": result["experiment_id"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
