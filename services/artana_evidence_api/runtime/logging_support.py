"""LiteLLM logging setup for runtime support."""

from __future__ import annotations

import importlib
import logging
import os
from contextlib import suppress

logger = logging.getLogger("artana_evidence_api.runtime")


def configure_litellm_runtime_logging() -> None:
    """Quiet LiteLLM's default stderr noise unless the caller opted in."""
    try:
        litellm = importlib.import_module("litellm")
        litellm_logging = importlib.import_module("litellm._logging")
    except ImportError:
        return

    with suppress(AttributeError):
        vars(litellm)["suppress_debug_info"] = True

    if os.getenv("LITELLM_LOG") is not None:
        return

    if hasattr(litellm_logging, "verbose_logger"):
        verbose_logger = litellm_logging.verbose_logger
        verbose_logger.setLevel(logging.CRITICAL)
        handlers = (
            verbose_logger.handlers if hasattr(verbose_logger, "handlers") else ()
        )
        for current_handler in handlers:
            current_handler.setLevel(logging.CRITICAL)

    if hasattr(litellm_logging, "handler"):
        current_handler = litellm_logging.handler
        current_handler.setLevel(logging.CRITICAL)


configure_litellm_runtime_logging()

__all__ = ["configure_litellm_runtime_logging", "logger"]
