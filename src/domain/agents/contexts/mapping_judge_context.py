"""Context model for mapper-judge agent pipelines."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import Field

from src.domain.agents.contexts.base import BaseAgentContext
from src.type_definitions.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from src.domain.agents.contracts.mapping_judge import MappingJudgeCandidate


class MappingJudgeContext(BaseAgentContext):
    """Execution context for one field-level mapping disambiguation."""

    field_key: str = Field(..., min_length=1, max_length=512)
    field_value_preview: str = Field(..., min_length=1, max_length=2000)
    source_id: str = Field(..., min_length=1, max_length=128)
    source_type: str | None = Field(default=None, max_length=64)
    domain_context: str | None = Field(default=None, max_length=64)
    record_metadata: JSONObject = Field(default_factory=dict)
    candidates: list[MappingJudgeCandidate] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


from src.domain.agents.contracts.mapping_judge import (  # noqa: TC001, E402
    MappingJudgeCandidate as _MappingJudgeCandidate,
)

MappingJudgeContext.model_rebuild(
    _types_namespace={"MappingJudgeCandidate": _MappingJudgeCandidate},
)

__all__ = ["MappingJudgeContext"]
