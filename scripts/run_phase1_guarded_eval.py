#!/usr/bin/env python3
"""Compatibility entrypoint for the Phase 1 guarded-evaluation workflow."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.phase1_guarded_eval.render import (  # noqa: E402
    _render_filtered_chase_summary,
    _selected_action_display,
    render_phase1_guarded_evaluation_markdown,
    write_phase1_guarded_evaluation_report,
)
from scripts.phase1_guarded_eval.report import (  # noqa: E402
    _build_guarded_graduation_gate,
    _build_guarded_report,
)
from scripts.phase1_guarded_eval.review import (  # noqa: E402
    _build_fixture_guarded_graduation_review,
    _build_fixture_review_summary,
)
from scripts.phase1_guarded_eval.runner import (  # noqa: E402
    _build_fixture_failure_compare_payload,
    _phase1_guarded_preflight,
    main,
    parse_args,
)

__all__ = [
    "_build_fixture_failure_compare_payload",
    "_build_fixture_guarded_graduation_review",
    "_build_fixture_review_summary",
    "_build_guarded_graduation_gate",
    "_build_guarded_report",
    "_phase1_guarded_preflight",
    "_render_filtered_chase_summary",
    "_selected_action_display",
    "main",
    "parse_args",
    "render_phase1_guarded_evaluation_markdown",
    "write_phase1_guarded_evaluation_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
