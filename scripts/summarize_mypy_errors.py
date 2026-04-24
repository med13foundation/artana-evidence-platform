"""Summarize mypy error output by code and file."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_ERROR_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+): error: (?P<message>.*?)(?:  \[(?P<code>[^\]]+)\])?$",
)


@dataclass(frozen=True, slots=True)
class MypyError:
    """One parsed mypy error line."""

    path: str
    line: int
    code: str
    message: str


def _read_text(path: str) -> str:
    if path == "-":
        import sys

        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _parse_errors(text: str) -> list[MypyError]:
    errors: list[MypyError] = []
    for line in text.splitlines():
        match = _ERROR_RE.match(line)
        if match is None:
            continue
        code = match.group("code") or "unknown"
        errors.append(
            MypyError(
                path=match.group("path"),
                line=int(match.group("line")),
                code=code,
                message=match.group("message"),
            ),
        )
    return errors


def _format_summary(
    *,
    label: str,
    errors: list[MypyError],
    top_files: int,
) -> str:
    by_code = Counter(error.code for error in errors)
    by_file = Counter(error.path for error in errors)
    unique_files = len(by_file)

    lines = [
        f"# mypy baseline: {label}",
        "",
        f"total_errors: {len(errors)}",
        f"files_with_errors: {unique_files}",
        "",
        "## errors_by_code",
    ]
    if by_code:
        for code, count in by_code.most_common():
            lines.append(f"- {code}: {count}")
    else:
        lines.append("- none: 0")

    lines.extend(["", "## top_files"])
    if by_file:
        for path, count in by_file.most_common(top_files):
            lines.append(f"- {path}: {count}")
    else:
        lines.append("- none: 0")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize mypy errors by error code and file.",
    )
    parser.add_argument("input", help="mypy output file, or '-' for stdin")
    parser.add_argument("--label", default="mypy", help="summary label")
    parser.add_argument(
        "--top-files",
        type=int,
        default=20,
        help="number of files to include in the file hotlist",
    )
    parser.add_argument("--output", help="optional summary output path")
    args = parser.parse_args()

    errors = _parse_errors(_read_text(str(args.input)))
    summary = _format_summary(
        label=str(args.label),
        errors=errors,
        top_files=int(args.top_files),
    )
    if args.output:
        output_path = Path(str(args.output))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(summary, encoding="utf-8")
    else:
        print(summary, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
