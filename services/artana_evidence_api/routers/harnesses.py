"""Harness discovery endpoints for the standalone harness service."""

from __future__ import annotations

from artana_evidence_api.auth import require_harness_read_access
from artana_evidence_api.harness_registry import (
    HarnessTemplate,
    get_harness_template,
    list_harness_templates,
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

router = APIRouter(
    prefix="/v1/harnesses",
    tags=["harnesses"],
    dependencies=[Depends(require_harness_read_access)],
)


class HarnessTemplateResponse(BaseModel):
    """Serialized harness template."""

    model_config = ConfigDict(strict=True)

    id: str
    display_name: str
    summary: str
    tool_groups: list[str]
    outputs: list[str]
    preloaded_skill_names: list[str]
    allowed_skill_names: list[str]
    default_run_budget: JSONObject | None = None

    @classmethod
    def from_template(
        cls,
        template: HarnessTemplate,
    ) -> HarnessTemplateResponse:
        """Build one response model from a harness template."""
        return cls(
            id=template.id,
            display_name=template.display_name,
            summary=template.summary,
            tool_groups=list(template.tool_groups),
            outputs=list(template.outputs),
            preloaded_skill_names=list(template.preloaded_skill_names),
            allowed_skill_names=list(template.allowed_skill_names),
            default_run_budget=template.default_run_budget,
        )


class HarnessTemplateListResponse(BaseModel):
    """List response for harness template discovery."""

    model_config = ConfigDict(strict=True)

    harnesses: list[HarnessTemplateResponse]
    total: int


@router.get("", response_model=HarnessTemplateListResponse, summary="List harnesses")
def list_harnesses() -> HarnessTemplateListResponse:
    """Return registered harness templates."""
    templates = list_harness_templates()
    return HarnessTemplateListResponse(
        harnesses=[
            HarnessTemplateResponse.from_template(template) for template in templates
        ],
        total=len(templates),
    )


@router.get(
    "/{harness_id}",
    response_model=HarnessTemplateResponse,
    summary="Get one harness",
)
def get_harness(harness_id: str) -> HarnessTemplateResponse:
    """Return one harness template by identifier."""
    template = get_harness_template(harness_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Harness '{harness_id}' not found",
        )
    return HarnessTemplateResponse.from_template(template)


__all__ = [
    "HarnessTemplateListResponse",
    "HarnessTemplateResponse",
    "get_harness",
    "list_harnesses",
    "router",
]
