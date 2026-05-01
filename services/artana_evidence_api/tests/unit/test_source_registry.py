"""Unit tests for public source capability registry."""

from __future__ import annotations

import inspect

import pytest
from artana_evidence_api import direct_source_search
from artana_evidence_api.routers import marrvel, pubmed
from artana_evidence_api.source_registry import (
    SourceCapability,
    SourceDefinition,
    default_research_plan_source_preferences,
    direct_search_source_keys,
    get_source_definition,
    list_source_definitions,
    normalize_source_key,
    research_plan_source_keys,
    unknown_source_preference_keys,
)
from pydantic import BaseModel, ValidationError


def test_source_registry_lists_all_research_plan_sources() -> None:
    definitions = list_source_definitions()
    source_keys = [definition.source_key for definition in definitions]

    assert source_keys == [
        "pubmed",
        "marrvel",
        "clinvar",
        "mondo",
        "pdf",
        "text",
        "drugbank",
        "alphafold",
        "gnomad",
        "uniprot",
        "hgnc",
        "clinical_trials",
        "mgi",
        "zfin",
    ]
    assert set(research_plan_source_keys()) == set(source_keys)


def test_source_registry_marks_direct_search_sources() -> None:
    assert direct_search_source_keys() == (
        "pubmed",
        "marrvel",
        "clinvar",
        "drugbank",
        "alphafold",
        "gnomad",
        "uniprot",
        "clinical_trials",
        "mgi",
        "zfin",
    )

    pubmed = get_source_definition("pubmed")
    marrvel = get_source_definition("marrvel")
    clinvar = get_source_definition("clinvar")
    clinical_trials = get_source_definition("clinical_trials")
    mondo = get_source_definition("mondo")
    direct_extra_sources = [
        get_source_definition(source_key)
        for source_key in (
            "drugbank",
            "alphafold",
            "gnomad",
            "uniprot",
            "mgi",
            "zfin",
        )
    ]

    assert pubmed is not None
    assert marrvel is not None
    assert clinvar is not None
    assert clinical_trials is not None
    assert mondo is not None
    assert all(source is not None for source in direct_extra_sources)
    assert SourceCapability.SEARCH in pubmed.capabilities
    assert SourceCapability.SEARCH in marrvel.capabilities
    assert SourceCapability.SEARCH in clinvar.capabilities
    assert SourceCapability.SEARCH in clinical_trials.capabilities
    for source in direct_extra_sources:
        assert source is not None
        assert SourceCapability.SEARCH in source.capabilities
        assert source.direct_search_enabled is True
        assert source.request_schema_ref is not None
        assert source.result_schema_ref is not None
    assert pubmed.direct_search_enabled is True
    assert pubmed.source_family == "literature"
    assert marrvel.direct_search_enabled is True
    assert clinvar.direct_search_enabled is True
    assert clinvar.source_family == "variant"
    assert clinical_trials.direct_search_enabled is True
    assert clinical_trials.source_family == "clinical"
    assert mondo.direct_search_enabled is False
    assert mondo.source_family == "ontology"
    assert clinvar.research_plan_enabled is True
    assert clinical_trials.research_plan_enabled is True
    assert clinvar.request_schema_ref == "ClinVarSourceSearchRequest"
    assert clinvar.result_schema_ref == "ClinVarSourceSearchResponse"
    assert (
        clinical_trials.request_schema_ref
        == "ClinicalTrialsSourceSearchRequest"
    )
    assert (
        clinical_trials.result_schema_ref
        == "ClinicalTrialsSourceSearchResponse"
    )


def test_direct_source_schema_refs_resolve_to_public_models() -> None:
    schema_objects: dict[str, object] = {}
    for schema_module in (direct_source_search, marrvel, pubmed):
        for schema_name in dir(schema_module):
            schema_objects[schema_name] = getattr(schema_module, schema_name)

    for source in list_source_definitions():
        if not source.direct_search_enabled:
            continue
        assert source.request_schema_ref is not None, source.source_key
        assert source.result_schema_ref is not None, source.source_key
        assert source.request_schema_ref in schema_objects, source.source_key
        assert source.result_schema_ref in schema_objects, source.source_key
        request_schema = schema_objects[source.request_schema_ref]
        result_schema = schema_objects[source.result_schema_ref]
        assert inspect.isclass(request_schema), source.source_key
        assert issubclass(request_schema, BaseModel), source.source_key
        assert inspect.isclass(result_schema), source.source_key
        assert issubclass(result_schema, BaseModel), source.source_key


def test_source_registry_defaults_match_research_init_behavior() -> None:
    assert default_research_plan_source_preferences() == {
        "pubmed": True,
        "marrvel": True,
        "clinvar": True,
        "mondo": True,
        "pdf": True,
        "text": True,
        "drugbank": False,
        "alphafold": False,
        "gnomad": False,
        "uniprot": False,
        "hgnc": False,
        "clinical_trials": False,
        "mgi": False,
        "zfin": False,
    }


def test_source_registry_normalizes_public_aliases() -> None:
    assert normalize_source_key("clinical-trials") == "clinical_trials"
    assert normalize_source_key("ClinicalTrials.gov") == "clinical_trials"
    assert get_source_definition("clinical-trials") == get_source_definition(
        "clinical_trials",
    )


def test_unknown_source_preference_keys_reports_bad_keys() -> None:
    assert unknown_source_preference_keys(
        {
            "pubmed": True,
            "clinical-trials": True,
            "made_up_source": True,
            123: True,
        },
    ) == ("123", "made_up_source")


def test_source_definition_rejects_inconsistent_capability_flags() -> None:
    with pytest.raises(ValidationError, match="direct_search_enabled"):
        SourceDefinition(
            source_key="bad_source",
            display_name="Bad Source",
            description="Invalid source definition.",
            source_family="variant",
            capabilities=(SourceCapability.RESEARCH_PLAN,),
            direct_search_enabled=True,
            research_plan_enabled=True,
            default_research_plan_enabled=False,
            live_network_required=False,
            requires_credentials=False,
            result_capture="Invalid.",
            proposal_flow="Invalid.",
        )


def test_source_definition_rejects_credential_names_without_requirement() -> None:
    with pytest.raises(ValidationError, match="credential_names"):
        SourceDefinition(
            source_key="bad_credentials",
            display_name="Bad Credentials",
            description="Invalid credential definition.",
            source_family="drug",
            capabilities=(SourceCapability.SEARCH, SourceCapability.RESEARCH_PLAN),
            direct_search_enabled=True,
            research_plan_enabled=True,
            default_research_plan_enabled=False,
            live_network_required=True,
            requires_credentials=False,
            credential_names=("BAD_CREDENTIAL",),
            result_capture="Invalid.",
            proposal_flow="Invalid.",
        )


def test_registered_source_capability_flags_are_consistent() -> None:
    for source in list_source_definitions():
        capabilities = set(source.capabilities)
        if source.direct_search_enabled:
            assert SourceCapability.SEARCH in capabilities
        if source.research_plan_enabled:
            assert SourceCapability.RESEARCH_PLAN in capabilities
        if source.default_research_plan_enabled:
            assert source.research_plan_enabled is True
        if source.requires_credentials:
            assert source.credential_names
        else:
            assert not source.credential_names
