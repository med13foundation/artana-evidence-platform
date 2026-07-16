"""Namespace-specific syntax checks for authoritative entity identifiers."""

from __future__ import annotations

import re

_CLINVAR_LOCAL_ID_RE = re.compile(
    r"^(?:[0-9]+|(?:RCV|SCV|VCV)[0-9]+(?:\.[0-9]+)?)$",
    flags=re.IGNORECASE,
)


def has_authority_compatible_identifier_syntax(curie: str) -> bool:
    """Return whether a CURIE has namespace-compatible authority syntax."""

    prefix, separator, local_id = curie.strip().partition(":")
    if separator == "" or local_id == "":
        return False
    if prefix.casefold() != "clinvar":
        return True
    return _CLINVAR_LOCAL_ID_RE.fullmatch(local_id) is not None


__all__ = ["has_authority_compatible_identifier_syntax"]
