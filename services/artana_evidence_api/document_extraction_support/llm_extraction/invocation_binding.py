"""Provider-visible binding between one model prompt and one local invocation."""

from __future__ import annotations

from dataclasses import dataclass

_HEADER = "ARTANA PROVIDER INVOCATION BINDING"
_FOOTER = "END ARTANA PROVIDER INVOCATION BINDING"
_MIN_BOUND_PROMPT_LINES = 7


@dataclass(frozen=True, slots=True)
class ProviderInvocationBinding:
    """Identifiers recovered from the provider-visible prompt envelope."""

    invocation_id: str
    kernel_run_id: str


def kernel_run_id_for_invocation(invocation_id: str) -> str:
    """Return the only valid extraction kernel namespace for an invocation."""

    _require_safe_identifier(invocation_id)
    return f"research-init-extraction:{invocation_id}"


def bind_prompt_to_invocation(*, prompt: str, invocation_id: str) -> str:
    """Prepend audit-only identifiers to the exact provider prompt."""

    if not prompt:
        raise ValueError("provider prompt must be nonempty")
    kernel_run_id = kernel_run_id_for_invocation(invocation_id)
    return (
        f"{_HEADER}\n"
        "This block is audit metadata, not biomedical source evidence.\n"
        f"artana_invocation_id={invocation_id}\n"
        f"artana_kernel_run_id={kernel_run_id}\n"
        f"{_FOOTER}\n\n"
        f"{prompt}"
    )


def parse_provider_invocation_binding(prompt: str) -> ProviderInvocationBinding:
    """Parse the unique leading binding envelope from a retrieved prompt."""

    lines = prompt.splitlines()
    if (
        len(lines) < _MIN_BOUND_PROMPT_LINES
        or lines[0] != _HEADER
        or lines[4] != _FOOTER
    ):
        raise ValueError("provider prompt lacks the invocation binding envelope")
    if lines[1] != "This block is audit metadata, not biomedical source evidence.":
        raise ValueError("provider prompt binding explanation was changed")
    invocation_id = _bound_value(lines[2], "artana_invocation_id")
    kernel_run_id = _bound_value(lines[3], "artana_kernel_run_id")
    expected_kernel_run_id = kernel_run_id_for_invocation(invocation_id)
    if kernel_run_id != expected_kernel_run_id:
        raise ValueError("provider prompt kernel binding does not match invocation")
    return ProviderInvocationBinding(
        invocation_id=invocation_id,
        kernel_run_id=kernel_run_id,
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


__all__ = [
    "ProviderInvocationBinding",
    "bind_prompt_to_invocation",
    "kernel_run_id_for_invocation",
    "parse_provider_invocation_binding",
]
