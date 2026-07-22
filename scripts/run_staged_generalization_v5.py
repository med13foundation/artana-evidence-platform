#!/usr/bin/env python3
"""Operate the staged-generalization V5 independent grading checkpoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    freeze_policy,
    verify_frozen_policy,
    write_contract_artifacts,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.grading.offline_replay import (
    write_replay,
)
from scripts.validation.public_gold.staged_event.generalization.grading.packets import (
    packet_json,
)
from scripts.validation.public_gold.staged_event.generalization.grading.preflight import (
    verify,
    write_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.grading.runner import (
    execute,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("prepare", "freeze", "replay", "preregister", "verify", "execute"),
    )
    parser.add_argument("--frozen-at")
    args = parser.parse_args()

    if args.action == "prepare":
        write_contract_artifacts(
            packet_path=DEFAULT_PATHS.grading.packet,
            schema_path=DEFAULT_PATHS.grading.schema,
            packet=packet_json(),
        )
        print(json.dumps({"status": "BLINDED_PACKETS_READY"}, sort_keys=True))
    elif args.action == "freeze":
        if not args.frozen_at:
            parser.error("freeze requires --frozen-at")
        policy = freeze_policy(
            DEFAULT_PATHS.grading,
            policy_id="staged-generalization-v5-dual-lane",
            frozen_at=args.frozen_at,
        )
        print(json.dumps({"policy_id": policy.policy_id}, sort_keys=True))
    elif args.action == "replay":
        write_replay(DEFAULT_PATHS.offline_replay)
        print(json.dumps({"status": "V4_REPLAY_WRITTEN"}, sort_keys=True))
    elif args.action == "preregister":
        write_candidate(DEFAULT_PATHS)
        print(json.dumps({"status": "V5_PREREGISTERED"}, sort_keys=True))
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
