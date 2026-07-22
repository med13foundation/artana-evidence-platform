#!/usr/bin/env python3
"""Operate the staged-generalization V8 polarity-taxonomy checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (  # noqa: E402
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v8.config import (  # noqa: E402
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v8.preflight import (  # noqa: E402
    verify,
    write_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v8.runner import (  # noqa: E402
    execute,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preregister", "verify", "execute"))
    args = parser.parse_args()

    if args.action == "preregister":
        write_candidate(DEFAULT_PATHS)
        print(json.dumps({"status": "V8_PREREGISTERED"}, sort_keys=True))
    elif args.action == "verify":
        verify_frozen_policy(DEFAULT_PATHS.grading)
        preregistration = verify(DEFAULT_PATHS)
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
