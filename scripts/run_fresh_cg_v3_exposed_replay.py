"""Run the offline-only Fresh-CG V3 exposed-case replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v3.runner import (  # noqa: E402
    preflight,
    replay,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "replay"))
    args = parser.parse_args()
    if args.command == "preflight":
        value = preflight()
    else:
        value = replay().model_dump(mode="json")
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
