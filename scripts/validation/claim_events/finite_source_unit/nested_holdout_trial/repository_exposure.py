"""Repository-wide exact-source exposure detection for hidden holdouts."""

from __future__ import annotations

import ast
import io
import json
import subprocess
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_REGULAR_GIT_MODES: Final = frozenset({"100644", "100755", "120000"})
_GIT_BATCH_HEADER_FIELD_COUNT: Final = 3
_SOURCE_TEXT_ENCODINGS: Final = (
    "utf-8",
    "utf-16-le",
    "utf-16-be",
    "utf-32-le",
    "utf-32-be",
    "latin-1",
    "cp1252",
)


@dataclass(frozen=True, slots=True)
class RepositorySourceIdentity:
    """One candidate source whose development visibility must be checked."""

    document_id: str
    unit_id: str
    text: str


@dataclass(frozen=True, slots=True)
class RepositorySourceExposure:
    """One exact source match in a tracked repository blob."""

    document_id: str
    unit_id: str
    path: str
    match_kind: str


@dataclass(frozen=True, slots=True)
class _TrackedBlob:
    path: str
    content: bytes


def find_repository_source_exposures(
    *,
    repository_root: Path,
    sources: tuple[RepositorySourceIdentity, ...],
) -> tuple[RepositorySourceExposure, ...]:
    """Find exact candidate text in the repository's tracked index snapshot."""

    _validate_sources(sources)
    _require_unmodified_tracked_worktree(repository_root)
    exposures: list[RepositorySourceExposure] = []
    for blob in _tracked_blobs(repository_root):
        decoded_values = _decoded_string_values(path=blob.path, content=blob.content)
        for source in sources:
            match_kind: str | None = None
            if _source_bytes_match(source.text, blob.content):
                match_kind = "TRACKED_TEXT"
            elif any(source.text in value for value in decoded_values):
                match_kind = "DECODED_STRING_VALUE"
            if match_kind is not None:
                exposures.append(
                    RepositorySourceExposure(
                        document_id=source.document_id,
                        unit_id=source.unit_id,
                        path=blob.path,
                        match_kind=match_kind,
                    ),
                )
    return tuple(
        sorted(
            exposures,
            key=lambda item: (item.document_id, item.unit_id, item.path),
        ),
    )


def _source_bytes_match(source_text: str, content: bytes) -> bool:
    for encoding in _SOURCE_TEXT_ENCODINGS:
        try:
            encoded_source = source_text.encode(encoding)
        except UnicodeEncodeError:
            continue
        if encoded_source in content:
            return True
    return False


def _validate_sources(sources: tuple[RepositorySourceIdentity, ...]) -> None:
    for source in sources:
        if not source.document_id.strip():
            raise ValueError("repository source document_id must be nonempty")
        if not source.unit_id.strip():
            raise ValueError("repository source unit_id must be nonempty")
        if not source.text.strip():
            raise ValueError("repository source text must be nonempty")


def _require_unmodified_tracked_worktree(repository_root: Path) -> None:
    completed = subprocess.run(
        ("git", "-C", str(repository_root), "diff", "--quiet", "--"),
        check=False,
    )
    if completed.returncode == 1:
        raise RuntimeError(
            "tracked worktree differs from the indexed repository snapshot",
        )
    if completed.returncode != 0:
        raise RuntimeError("could not verify tracked repository state")


def _tracked_blobs(repository_root: Path) -> tuple[_TrackedBlob, ...]:
    completed = subprocess.run(
        ("git", "-C", str(repository_root), "ls-files", "--stage", "-z"),
        check=True,
        capture_output=True,
    )
    entries: list[tuple[str, str]] = []
    for raw_entry in completed.stdout.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", maxsplit=1)
        mode, object_id, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise RuntimeError("repository index contains unresolved merge stages")
        if mode in _REGULAR_GIT_MODES:
            entries.append((raw_path.decode("utf-8"), object_id))
    contents = _read_git_objects(
        repository_root=repository_root,
        object_ids=tuple(object_id for _, object_id in entries),
    )
    return tuple(
        _TrackedBlob(path=path, content=content)
        for (path, _), content in zip(entries, contents, strict=True)
    )


def _read_git_objects(
    *,
    repository_root: Path,
    object_ids: tuple[str, ...],
) -> tuple[bytes, ...]:
    if not object_ids:
        return ()
    completed = subprocess.run(
        ("git", "-C", str(repository_root), "cat-file", "--batch"),
        input=("\n".join(object_ids) + "\n").encode(),
        check=True,
        capture_output=True,
    )
    output = completed.stdout
    cursor = 0
    contents: list[bytes] = []
    for expected_object_id in object_ids:
        header_end = output.find(b"\n", cursor)
        if header_end < 0:
            raise RuntimeError("truncated git object header")
        header = output[cursor:header_end].decode("ascii").split()
        if len(header) != _GIT_BATCH_HEADER_FIELD_COUNT:
            raise RuntimeError("tracked repository object is unavailable")
        object_id, object_type, raw_size = header
        if object_id != expected_object_id or object_type != "blob":
            raise RuntimeError("tracked repository object identity changed")
        size = int(raw_size)
        content_start = header_end + 1
        content_end = content_start + size
        if content_end >= len(output) or output[content_end : content_end + 1] != b"\n":
            raise RuntimeError("truncated tracked repository object")
        contents.append(output[content_start:content_end])
        cursor = content_end + 1
    if cursor != len(output):
        raise RuntimeError("unexpected data followed tracked repository objects")
    return tuple(contents)


def _decoded_string_values(*, path: str, content: bytes) -> tuple[str, ...]:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return _python_string_values(path=path, content=content)
    if suffix == ".json":
        return tuple(_walk_json_strings(_parse_json(path=path, content=content)))
    if suffix == ".jsonl":
        values: list[str] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if line.strip():
                values.extend(
                    _walk_json_strings(
                        _parse_json(
                            path=f"{path}:{line_number}",
                            content=line,
                        ),
                    ),
                )
        return tuple(values)
    return ()


def _python_string_values(*, path: str, content: bytes) -> tuple[str, ...]:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
        text = content.decode(encoding)
        tree = ast.parse(text)
    except (LookupError, SyntaxError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"could not parse tracked Python source: {path}") from exc
    values = {
        value
        for node in ast.walk(tree)
        if (value := _constant_string_value(node)) is not None
    }
    return tuple(sorted(values))


def _constant_string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _constant_string_value(node.left)
        right = _constant_string_value(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts = tuple(_constant_string_value(value) for value in node.values)
        if all(part is not None for part in parts):
            return "".join(part for part in parts if part is not None)
    return None


def _parse_json(*, path: str, content: bytes) -> object:
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not parse tracked JSON source: {path}") from exc


def _walk_json_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(item for child in value for item in _walk_json_strings(child))
    if isinstance(value, dict):
        return tuple(
            item
            for key, child in value.items()
            for item in (*_walk_json_strings(key), *_walk_json_strings(child))
        )
    return ()


__all__ = [
    "RepositorySourceExposure",
    "RepositorySourceIdentity",
    "find_repository_source_exposures",
]
