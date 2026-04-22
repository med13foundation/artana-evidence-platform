#!/usr/bin/env python3
"""Generate a GitHub issue triage health report for the monorepo."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final

TRIAGE_LABELS: Final[tuple[str, ...]] = ("triage:P0", "triage:P1", "triage:P2", "triage:P3")
TOPIC_LABELS: Final[tuple[str, ...]] = (
    "security",
    "performance",
    "testing",
    "architecture",
    "observability",
    "documentation",
    "evidence-api-review",
)


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    url: str
    updated_at: datetime
    labels: tuple[str, ...]
    assignees: tuple[str, ...]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Repository in owner/name form.")
    parser.add_argument("--limit", type=int, default=200, help="Maximum number of open issues to inspect.")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=7,
        help="Number of days without updates before a P0/P1 issue is considered stale.",
    )
    return parser.parse_args()


def _require_dict(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected {field_name} to be an object.")
    return value


def _require_list(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"Expected {field_name} to be a list.")
    return value


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"Expected {field_name} to be an integer.")
    return value


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Expected {field_name} to be a string.")
    return value


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
      return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_issues(repo: str, limit: int) -> list[Issue]:
    command = [
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        "number,title,url,labels,assignees,updatedAt",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "gh issue list failed")

    payload = json.loads(completed.stdout)
    raw_issues = _require_list(payload, "issues payload")
    issues: list[Issue] = []

    for raw_issue in raw_issues:
        issue_dict = _require_dict(raw_issue, "issue")
        label_names = tuple(
            _require_str(_require_dict(raw_label, "label").get("name"), "label.name")
            for raw_label in _require_list(issue_dict.get("labels"), "issue.labels")
        )
        assignee_names = tuple(
            _require_str(_require_dict(raw_assignee, "assignee").get("login"), "assignee.login")
            for raw_assignee in _require_list(issue_dict.get("assignees"), "issue.assignees")
        )
        issues.append(
            Issue(
                number=_require_int(issue_dict.get("number"), "issue.number"),
                title=_require_str(issue_dict.get("title"), "issue.title"),
                url=_require_str(issue_dict.get("url"), "issue.url"),
                updated_at=_parse_datetime(_require_str(issue_dict.get("updatedAt"), "issue.updatedAt")),
                labels=label_names,
                assignees=assignee_names,
            )
        )

    return issues


def _count_by_label(issues: list[Issue], labels: tuple[str, ...]) -> dict[str, int]:
    return {label: sum(1 for issue in issues if label in issue.labels) for label in labels}


def _priority_of(issue: Issue) -> str | None:
    for label in TRIAGE_LABELS:
        if label in issue.labels:
            return label
    return None


def _format_issue_line(issue: Issue) -> str:
    assignee_text = ", ".join(issue.assignees) if issue.assignees else "unassigned"
    priority = _priority_of(issue) or "untriaged"
    updated = issue.updated_at.date().isoformat()
    return f"- [#{issue.number}]({issue.url}) {issue.title} ({priority}; {assignee_text}; updated {updated})"


def _format_issue_section(title: str, issues: list[Issue], empty_message: str) -> list[str]:
    lines = [f"## {title}"]
    if not issues:
        lines.append(empty_message)
        lines.append("")
        return lines

    for issue in issues:
        lines.append(_format_issue_line(issue))
    lines.append("")
    return lines


def _build_report(repo: str, issues: list[Issue], stale_days: int) -> str:
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(days=stale_days)

    unlabeled = [issue for issue in issues if not issue.labels]
    unassigned = [issue for issue in issues if not issue.assignees]
    blocked = [issue for issue in issues if "triage:blocked" in issue.labels]

    p0_or_p1_unassigned = [
        issue
        for issue in issues
        if _priority_of(issue) in {"triage:P0", "triage:P1"} and not issue.assignees
    ]
    stale_priority = [
        issue
        for issue in issues
        if _priority_of(issue) in {"triage:P0", "triage:P1"} and issue.updated_at < stale_before
    ]

    priority_counts = _count_by_label(issues, TRIAGE_LABELS)
    topic_counts = _count_by_label(issues, TOPIC_LABELS)

    lines = [
        "# GitHub triage health",
        "",
        f"- Repository: `{repo}`",
        f"- Generated at: `{now.isoformat(timespec='seconds')}`",
        f"- Open issues inspected: `{len(issues)}`",
        f"- Unassigned issues: `{len(unassigned)}`",
        f"- Unlabeled issues: `{len(unlabeled)}`",
        "",
        "## Priority mix",
        f"- triage:P0: `{priority_counts['triage:P0']}`",
        f"- triage:P1: `{priority_counts['triage:P1']}`",
        f"- triage:P2: `{priority_counts['triage:P2']}`",
        f"- triage:P3: `{priority_counts['triage:P3']}`",
        "",
        "## Topic mix",
        f"- security: `{topic_counts['security']}`",
        f"- performance: `{topic_counts['performance']}`",
        f"- testing: `{topic_counts['testing']}`",
        f"- architecture: `{topic_counts['architecture']}`",
        f"- observability: `{topic_counts['observability']}`",
        f"- documentation: `{topic_counts['documentation']}`",
        f"- evidence-api-review: `{topic_counts['evidence-api-review']}`",
        "",
    ]

    lines.extend(
        _format_issue_section(
            "Immediate attention",
            p0_or_p1_unassigned,
            "No unassigned P0/P1 issues. The urgent queue currently has owners.",
        )
    )
    lines.extend(
        _format_issue_section(
            "Unlabeled intake gaps",
            unlabeled,
            "No unlabeled open issues. Intake hygiene is healthy.",
        )
    )
    lines.extend(
        _format_issue_section(
            "Blocked work",
            blocked,
            "No issues are currently labeled `triage:blocked`.",
        )
    )
    lines.extend(
        _format_issue_section(
            f"Stale P0/P1 work ({stale_days}+ days without updates)",
            stale_priority,
            "No stale P0/P1 issues. Urgent work is seeing active updates.",
        )
    )

    lines.extend(
        [
            "## Recommended next moves",
            "- Assign owners to every P0 and P1 issue before pulling more P2/P3 work.",
            "- Label every new issue within one business day so the project inbox stays filterable.",
            "- Break epics into sub-issues and use the project board for current state, not labels.",
            "- Keep labels for taxonomy (`security`, `testing`, `performance`) and use the GitHub Project `Status` field for workflow state.",
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> int:
    args = _parse_args()
    try:
        issues = _load_issues(repo=args.repo, limit=args.limit)
        report = _build_report(repo=args.repo, issues=issues, stale_days=args.stale_days)
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"error: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
