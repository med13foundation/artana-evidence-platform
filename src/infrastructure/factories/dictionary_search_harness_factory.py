"""Factory helpers for selecting the dictionary search harness implementation."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.infrastructure.llm.adapters.deterministic_dictionary_search_harness_adapter import (
    DeterministicDictionarySearchHarnessAdapter,
)
from src.infrastructure.llm.adapters.dictionary_search_harness_adapter import (
    ArtanaDictionarySearchHarnessAdapter,
)

if TYPE_CHECKING:
    from artana_evidence_db.governance_ports import (
        DictionarySearchHarnessPort,
    )
    from artana_evidence_db.kernel_repositories import (
        DictionaryRepository,
    )

    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.domain.ports.text_embedding_port import TextEmbeddingPort

_ENV_ENABLE_DICTIONARY_SEARCH_HARNESS = "ARTANA_ENABLE_DICTIONARY_SEARCH_HARNESS"


def create_dictionary_search_harness(
    *,
    dictionary_repo: DictionaryRepository,
    embedding_provider: TextEmbeddingPort | None,
    mapping_judge_agent: MappingJudgePort | None = None,
) -> DictionarySearchHarnessPort:
    """Build the configured dictionary search harness implementation."""
    if os.getenv(_ENV_ENABLE_DICTIONARY_SEARCH_HARNESS, "1").strip() != "1":
        return DeterministicDictionarySearchHarnessAdapter(
            dictionary_repo=dictionary_repo,
            embedding_provider=embedding_provider,
        )

    return ArtanaDictionarySearchHarnessAdapter(
        dictionary_repo=dictionary_repo,
        embedding_provider=embedding_provider,
        mapping_judge_agent=mapping_judge_agent,
    )
