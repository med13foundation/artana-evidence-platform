#!/usr/bin/env bash

# Check the current branch's GitHub PR checks when gh/PR context is available.

set -euo pipefail

REQUIRE_GITHUB_PR_CHECKS="${REQUIRE_GITHUB_PR_CHECKS:-0}"
CHECK_FIELDS="name,state,bucket,link,workflow"
FAIL_FILTER='
  (((.bucket // "") | ascii_downcase) == "fail")
  or (((.state // "") | ascii_downcase) == "failure")
  or (((.state // "") | ascii_downcase) == "error")
  or (((.state // "") | ascii_downcase) == "cancelled")
  or (((.state // "") | ascii_downcase) == "timed_out")
  or (((.state // "") | ascii_downcase) == "action_required")
'
PENDING_FILTER='
  (((.bucket // "") | ascii_downcase) == "pending")
  or (((.state // "") | ascii_downcase) == "pending")
  or (((.state // "") | ascii_downcase) == "queued")
  or (((.state // "") | ascii_downcase) == "in_progress")
  or (((.state // "") | ascii_downcase) == "waiting")
  or (((.state // "") | ascii_downcase) == "requested")
  or (((.state // "") | ascii_downcase) == "expected")
'

skip_or_stop() {
    local message="$1"
    if [ "$REQUIRE_GITHUB_PR_CHECKS" = "1" ]; then
        echo "$message"
        exit 1
    fi
    echo "$message; skipping."
    exit 0
}

if ! command -v gh >/dev/null 2>&1; then
    skip_or_stop "GitHub PR checks unavailable: gh not found"
fi

if ! gh auth status >/dev/null 2>&1; then
    skip_or_stop "GitHub PR checks unavailable: gh auth is not ready"
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$repo_root" ]; then
    skip_or_stop "GitHub PR checks unavailable: not inside a git repo"
fi

if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
    skip_or_stop "GitHub PR checks unavailable: worktree has uncommitted changes"
fi

pr_number="$(gh pr view --json number --jq '.number' 2>/dev/null || true)"
if [ -z "$pr_number" ]; then
    skip_or_stop "GitHub PR checks unavailable: no current branch PR"
fi

pr_url="$(gh pr view --json url --jq '.url' 2>/dev/null || true)"

if ! total_count="$(gh pr checks "$pr_number" --json "$CHECK_FIELDS" --jq 'length' 2>/dev/null)"; then
    echo "GitHub PR checks could not be inspected for PR #$pr_number."
    exit 1
fi

if [ "$total_count" = "0" ]; then
    echo "GitHub PR checks: PR #$pr_number has no reported checks yet."
    exit 0
fi

failing_count="$(
    gh pr checks "$pr_number" \
        --json "$CHECK_FIELDS" \
        --jq "[.[] | select($FAIL_FILTER)] | length"
)"
pending_count="$(
    gh pr checks "$pr_number" \
        --json "$CHECK_FIELDS" \
        --jq "[.[] | select($PENDING_FILTER)] | length"
)"
passing_count="$(
    gh pr checks "$pr_number" \
        --json "$CHECK_FIELDS" \
        --jq '[.[] | select(((.bucket // "") | ascii_downcase) == "pass")] | length'
)"
skipped_count="$(
    gh pr checks "$pr_number" \
        --json "$CHECK_FIELDS" \
        --jq '[.[] | select(((.bucket // "") | ascii_downcase) == "skipping")] | length'
)"

if [ "$failing_count" != "0" ]; then
    echo "GitHub PR checks: red=$failing_count pending=$pending_count green=$passing_count skipped=$skipped_count total=$total_count"
    if [ -n "$pr_url" ]; then
        echo "PR: $pr_url"
    fi

    inspector="${GH_FIX_CI_INSPECTOR:-}"
    default_inspector="$HOME/.codex/skills/gh-fix-ci/scripts/inspect_pr_checks.py"
    if [ -z "$inspector" ] && [ -f "$default_inspector" ]; then
        inspector="$default_inspector"
    fi

    if [ -n "$inspector" ] && command -v python3 >/dev/null 2>&1; then
        python3 "$inspector" --repo "$repo_root" --pr "$pr_number" --max-lines 120 --context 30 || true
    else
        gh pr checks "$pr_number" \
            --json "$CHECK_FIELDS" \
            --jq ".[] | select($FAIL_FILTER) | \"- \" + .name + \" [\" + (.workflow // \"workflow\") + \"] \" + (.link // \"\")"
    fi
    exit 1
fi

echo "GitHub PR checks: red=0 pending=$pending_count green=$passing_count skipped=$skipped_count total=$total_count"
if [ -n "$pr_url" ]; then
    echo "PR: $pr_url"
fi
