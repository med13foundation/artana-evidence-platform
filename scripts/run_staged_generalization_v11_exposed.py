#!/usr/bin/env python3
"""Preregister, verify, or execute the V11 exposed/public model gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.public_gold.staged_event.generalization.repair_v11.config import (  # noqa: E402
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.preflight import (  # noqa: E402
    verify,
    write_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.runner import (  # noqa: E402
    execute,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preregister", "verify", "execute"))
    args = parser.parse_args()

    if args.action == "preregister":
        write_candidate(DEFAULT_PATHS)
        result = verify(DEFAULT_PATHS)
        print(
            json.dumps(
                {
                    "status": "V11_EXPOSED_EXECUTION_PREREGISTERED",
                    "experiment_id": result["experiment_id"],
                },
                sort_keys=True,
            )
        )
    elif args.action == "verify":
        result = verify(DEFAULT_PATHS, remote_gate=True)
        print(
            json.dumps(
                {
                    "status": "V11_EXPOSED_EXECUTION_PREFLIGHT_PASS",
                    "experiment_id": result["experiment_id"],
                },
                sort_keys=True,
            )
        )
    else:
        print(execute())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
