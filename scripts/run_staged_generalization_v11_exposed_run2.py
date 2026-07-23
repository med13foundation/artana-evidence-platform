#!/usr/bin/env python3
"""Prepare, qualify, preregister, verify, or execute V11 exposed run 2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.artifacts import (  # noqa: E402
    write_operational_artifacts,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.config import (  # noqa: E402
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.preflight import (  # noqa: E402
    verify,
    write_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.prior_qualification import (  # noqa: E402
    write_usage_addendum,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.qualification import (  # noqa: E402
    execute_qualification,
    verify_qualification_preregistration,
    write_qualification_preregistration,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.runner import (  # noqa: E402
    execute,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=(
            "qualification-preregister",
            "qualification-verify",
            "qualification-execute",
            "preregister",
            "verify",
            "execute",
        ),
    )
    args = parser.parse_args()

    if args.action == "qualification-preregister":
        write_operational_artifacts(DEFAULT_PATHS)
        write_usage_addendum(DEFAULT_PATHS)
        write_qualification_preregistration(DEFAULT_PATHS)
        result = verify_qualification_preregistration(DEFAULT_PATHS)
        status = "V11_FOREGROUND_QUALIFICATION_PREREGISTERED"
    elif args.action == "qualification-verify":
        result = verify_qualification_preregistration(
            DEFAULT_PATHS,
            remote_gate=True,
        )
        status = "V11_FOREGROUND_QUALIFICATION_PREFLIGHT_PASS"
    elif args.action == "qualification-execute":
        print(execute_qualification(DEFAULT_PATHS))
        return 0
    elif args.action == "preregister":
        write_candidate(DEFAULT_PATHS)
        result = verify(DEFAULT_PATHS)
        status = "V11_EXPOSED_RUN_V2_PREREGISTERED"
    elif args.action == "verify":
        result = verify(DEFAULT_PATHS, remote_gate=True)
        status = "V11_EXPOSED_RUN_V2_PREFLIGHT_PASS"
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
