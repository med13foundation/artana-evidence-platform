"""Provider-visible binding between one model prompt and one local invocation."""

from __future__ import annotations

from dataclasses import dataclass

_HEADER = "ARTANA PROVIDER INVOCATION BINDING"
_FOOTER = "END ARTANA PROVIDER INVOCATION BINDING"
_MIN_BOUND_PROMPT_LINES = 10
_SHA256_LENGTH = 64


@dataclass(frozen=True, slots=True)
class ProviderInvocationBinding:
    """Identifiers recovered from the provider-visible prompt envelope."""

    invocation_id: str
    kernel_run_id: str
    source_sha256: str
    input_sha256: str
    evidence_unit_sha256: str


def kernel_run_id_for_invocation(invocation_id: str) -> str:
    """Return the only valid extraction kernel namespace for an invocation."""

    _require_safe_identifier(invocation_id)
    return f"research-init-extraction:{invocation_id}"


def bind_prompt_to_invocation(
    *,
    prompt: str,
    invocation_id: str,
    source_sha256: str,
    input_sha256: str,
    evidence_unit_sha256: str,
) -> str:
    """Prepend audit-only identifiers to the exact provider prompt."""

    if not prompt:
        raise ValueError("provider prompt must be nonempty")
    _require_sha256(source_sha256, field_name="source_sha256")
    _require_sha256(input_sha256, field_name="input_sha256")
    _require_sha256(evidence_unit_sha256, field_name="evidence_unit_sha256")
    kernel_run_id = kernel_run_id_for_invocation(invocation_id)
    return (
        f"{_HEADER}\n"
        "This block is audit metadata, not biomedical source evidence.\n"
        f"artana_invocation_id={invocation_id}\n"
        f"artana_kernel_run_id={kernel_run_id}\n"
        f"artana_source_sha256={source_sha256}\n"
        f"artana_input_sha256={input_sha256}\n"
        f"artana_evidence_unit_sha256={evidence_unit_sha256}\n"
        f"{_FOOTER}\n\n"
        f"{prompt}"
    )


def parse_provider_invocation_binding(prompt: str) -> ProviderInvocationBinding:
    """Parse the unique leading binding envelope from a retrieved prompt."""

    lines = prompt.splitlines()
    if (
        len(lines) < _MIN_BOUND_PROMPT_LINES
        or lines[0] != _HEADER
        or lines[7] != _FOOTER
    ):
        raise ValueError("provider prompt lacks the invocation binding envelope")
    if lines[1] != "This block is audit metadata, not biomedical source evidence.":
        raise ValueError("provider prompt binding explanation was changed")
    invocation_id = _bound_value(lines[2], "artana_invocation_id")
    kernel_run_id = _bound_value(lines[3], "artana_kernel_run_id")
    source_sha256 = _bound_value(lines[4], "artana_source_sha256")
    input_sha256 = _bound_value(lines[5], "artana_input_sha256")
    evidence_unit_sha256 = _bound_value(
        lines[6],
        "artana_evidence_unit_sha256",
    )
    _require_sha256(source_sha256, field_name="source_sha256")
    _require_sha256(input_sha256, field_name="input_sha256")
    _require_sha256(evidence_unit_sha256, field_name="evidence_unit_sha256")
    expected_kernel_run_id = kernel_run_id_for_invocation(invocation_id)
    if kernel_run_id != expected_kernel_run_id:
        raise ValueError("provider prompt kernel binding does not match invocation")
    return ProviderInvocationBinding(
        invocation_id=invocation_id,
        kernel_run_id=kernel_run_id,
        source_sha256=source_sha256,
        input_sha256=input_sha256,
        evidence_unit_sha256=evidence_unit_sha256,
    )


def _bound_value(line: str, key: str) -> str:
    prefix = f"{key}="
    if not line.startswith(prefix):
        raise ValueError(f"provider prompt binding lacks {key}")
    value = line.removeprefix(prefix)
    _require_safe_identifier(value)
    return value


def _require_safe_identifier(value: str) -> None:
    if not value or value.strip() != value or "\n" in value or "\r" in value:
        raise ValueError("provider invocation identifier must be one nonempty line")


def _require_sha256(value: str, *, field_name: str) -> None:
    if len(value) != _SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"provider invocation {field_name} must be lowercase SHA-256")


__all__ = [
    "ProviderInvocationBinding",
    "bind_prompt_to_invocation",
    "kernel_run_id_for_invocation",
    "parse_provider_invocation_binding",
]
