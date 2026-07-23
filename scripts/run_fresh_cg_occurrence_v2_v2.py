#!/usr/bin/env python3
"""Prepare, verify, or execute the forward-only Fresh-CG V2 experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.config import (  # noqa: E402
    DEFAULT_PATHS,
    REPO,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.preflight import (  # noqa: E402
    verify,
    write_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.review import (  # noqa: E402
    compose_primary_reviewers,
    compose_tiebreaker,
    write_reference,
    write_review_packet,
    write_tiebreak_request,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.runner import (  # noqa: E402
    execute,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.selection import (  # noqa: E402
    write_selection,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=(
            "selection",
            "review-packet",
            "compose-primaries",
            "tiebreak-request",
            "reference",
            "preregister",
            "verify",
            "execute",
        ),
    )
    args = parser.parse_args()

    if args.action == "selection":
        development = REPO / (
            "validation/public_gold/bionlp_cg/raw/"
            "bionlp-st-2013-cg-master/original-data/devel"
        )
        write_selection(DEFAULT_PATHS.selection, development)
        status = "FRESH_CG_V2_SELECTION_FROZEN"
    elif args.action == "review-packet":
        write_review_packet(DEFAULT_PATHS)
        status = "FRESH_CG_V2_REVIEW_PACKET_FROZEN"
    elif args.action == "compose-primaries":
        compose_primary_reviewers(DEFAULT_PATHS)
        status = "FRESH_CG_V2_PRIMARY_REVIEWS_COMPOSED"
    elif args.action == "tiebreak-request":
        write_tiebreak_request(DEFAULT_PATHS)
        status = "FRESH_CG_V2_TIEBREAK_REQUEST_FROZEN"
    elif args.action == "reference":
        compose_tiebreaker(DEFAULT_PATHS)
        write_reference(DEFAULT_PATHS)
        status = "FRESH_CG_V2_REFERENCE_FROZEN"
    elif args.action == "preregister":
        write_candidate(DEFAULT_PATHS)
        status = "FRESH_CG_V2_PREREGISTERED"
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
        return 0
    else:
        print(execute())
        return 0
    print(json.dumps({"status": status}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
