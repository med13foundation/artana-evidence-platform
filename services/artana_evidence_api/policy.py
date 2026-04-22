"""Kernel policy helpers for the graph-harness service."""

from __future__ import annotations

from artana.kernel import KernelPolicy


def build_graph_harness_policy() -> KernelPolicy:
    """Return the default OS-grade safety policy for harness kernel runs."""
    return KernelPolicy.enforced_v2()


__all__ = ["build_graph_harness_policy"]
