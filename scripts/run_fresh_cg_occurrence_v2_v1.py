#!/usr/bin/env python3
"""Preregister, verify, or execute the fresh-CG occurrence-V2 experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.config import (  # noqa: E402
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.preflight import (  # noqa: E402
    verify,
    write_candidate,
    write_reference_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.runner import (  # noqa: E402
    execute,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("reference", "preregister", "verify", "execute"),
    )
    args = parser.parse_args()

    if args.action == "reference":
        write_reference_candidate(DEFAULT_PATHS)
        print(json.dumps({"status": "FRESH_CG_REFERENCE_FROZEN"}, sort_keys=True))
    elif args.action == "preregister":
        write_candidate(DEFAULT_PATHS)
        print(json.dumps({"status": "FRESH_CG_PREREGISTERED"}, sort_keys=True))
    elif args.action == "verify":
        preregistration = verify(
            DEFAULT_PATHS,
            remote_gate=True,
            offline_regression=True,
        )
        print(
            json.dumps(
                {"experiment_id": preregistration["experiment_id"]},
                sort_keys=True,
            )
        )
    else:
        print(execute())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
