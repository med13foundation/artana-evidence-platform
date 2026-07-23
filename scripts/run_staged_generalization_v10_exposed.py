#!/usr/bin/env python3
"""Preregister, verify, or execute the V10 exposed/public model gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (  # noqa: E402
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_preflight import (  # noqa: E402
    verify,
    write_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_runner import (  # noqa: E402
    execute,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.historical_v9 import (  # noqa: E402
    verify_provenance,
    write_provenance,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("provenance", "preregister", "verify", "execute"),
    )
    args = parser.parse_args()

    if args.action == "provenance":
        write_provenance(DEFAULT_PATHS)
        result = verify_provenance(DEFAULT_PATHS)
        print(
            json.dumps(
                {
                    "status": "V9_HISTORICAL_REPRODUCIBILITY_ISOLATED",
                    "historical_pinned_commit": result["historical_pinned_commit"],
                },
                sort_keys=True,
            )
        )
    elif args.action == "preregister":
        write_candidate(DEFAULT_PATHS)
        result = verify(DEFAULT_PATHS)
        print(
            json.dumps(
                {
                    "status": "V10_EXPOSED_EXECUTION_PREREGISTERED",
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
                    "status": "V10_EXPOSED_EXECUTION_PREFLIGHT_PASS",
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
