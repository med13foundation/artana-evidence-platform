#!/usr/bin/env python3
"""Preregister, verify, or execute the bounded V17 exposed gate."""

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

from scripts.validation.public_gold.staged_event.generalization.repair_v17.config import (  # noqa: E402
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.preflight import (  # noqa: E402
    verify,
    write_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.runner import (  # noqa: E402
    execute,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preregister", "verify", "execute"))
    args = parser.parse_args()
    if args.action == "preregister":
        write_candidate(DEFAULT_PATHS)
        result = verify(
            DEFAULT_PATHS,
            require_package_review=False,
            require_tracked_dependencies=False,
        )
        status = "V17_EXPOSED_GATE_PREREGISTERED"
    elif args.action == "verify":
        result = verify(DEFAULT_PATHS, remote_gate=True)
        status = "V17_EXPOSED_GATE_PREFLIGHT_PASS"
    else:
        print(execute())
        return 0
    print(
        json.dumps(
            {
                "status": status,
                "experiment_id": result["experiment_id"],
                "preregistration_sha256": result["preregistration_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
