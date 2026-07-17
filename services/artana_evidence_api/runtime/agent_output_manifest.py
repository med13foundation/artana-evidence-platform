"""Versioned registry for production agent output schema boundaries."""

from __future__ import annotations

from collections.abc import Mapping

from artana_evidence_api.runtime.agent_output_schema import (
    AgentOutputSchemaPolicy,
    AgentOutputSchemaRegistry,
    CategoryFieldPolicy,
    CategoryValuePolicy,
    NumericFieldPolicy,
    NumericOrigin,
)


def _category(
    path: str,
    definitions: Mapping[str, str],
    *,
    evidence_requirement: str,
    invalid_behavior: str = "Reject the model output and record an invalid response.",
    allow_schema_subset: bool = False,
    debt_id: str | None = None,
) -> CategoryFieldPolicy:
    return CategoryFieldPolicy(
        path=path,
        values=tuple(
            CategoryValuePolicy(
                value=value,
                definition=definition,
                positive_example=f"Use {value!r} only when {definition}",
                counterexample=f"Do not use {value!r} when that observable condition is absent.",
            )
            for value, definition in definitions.items()
        ),
        evidence_requirement=evidence_requirement,
        invalid_behavior=invalid_behavior,
        allow_schema_subset=allow_schema_subset,
        debt_id=debt_id,
    )


_SOURCE_TYPE = {
    "tool": "the cited evidence is a recorded tool result.",
    "db": "the cited evidence is a database record with a stable locator.",
    "paper": "the cited evidence is a paper span with a stable citation.",
    "web": "the cited evidence is a web resource with a stable URL.",
    "note": "the cited evidence is a user or workflow note with a stable locator.",
    "api": "the cited evidence is a recorded API response with a stable locator.",
}
_RUN_DECISION = {
    "generated": "the agent produced a schema-valid result from cited evidence.",
    "fallback": "the result came from an explicitly recorded non-agent fallback path.",
    "escalate": "missing or conflicting evidence requires human review.",
}
_CLAIM_POLARITY = {
    "SUPPORT": "the cited source directly asserts the claim in the positive direction.",
    "REFUTE": "the cited source directly contradicts or negates the claim.",
    "UNCERTAIN": "the cited source leaves the claim direction unresolved.",
    "HYPOTHESIS": "the cited source presents the claim as a hypothesis.",
    "NULL_RESULT": "the cited source reports no supported effect or association.",
}
_CLAIM_EPISTEMIC_STATUS = {
    "ASSERTED": "the cited source states the finding as an observed conclusion.",
    "PROVISIONAL": "the cited source marks the finding as preliminary or conditional.",
    "UNCERTAIN": "the cited source explicitly leaves the finding uncertain.",
    "HYPOTHESIS": "the cited source proposes the finding for future testing.",
    "NULL_RESULT": "the cited source reports a null or threshold-failing result.",
}
_INVENTORY_POLARITY = {
    "SUPPORT": "the source presents the described relation or effect.",
    "REFUTE": "the source explicitly contradicts the described relation or effect.",
    "NULL_RESULT": "the source reports no supported effect or association.",
}
_INVENTORY_EPISTEMIC_STATUS = {
    "ASSERTED": "the source states the finding as an observed conclusion.",
    "PROVISIONAL": "the source marks the finding as preliminary or conditional.",
    "UNCERTAIN": "the source explicitly leaves the finding uncertain.",
    "HYPOTHESIS": "the source proposes the finding for future testing.",
}
_CLAIM_KIND = {
    "SCIENTIFIC_FINDING": "the source reports a biological relationship or result.",
    "SCIENTIFIC_HYPOTHESIS": "the source explicitly proposes a scientific explanation or mechanism.",
    "PROCEDURAL_CONTEXT": "the source describes an action without reporting a scientific result.",
    "MEASUREMENT_ONLY": "the source reports measurement without a result, comparison, or conclusion.",
    "AMBIGUOUS": "the frozen source cannot safely resolve whether the statement is a scientific claim.",
}
_CLAIM_QUALIFIER_STATE = {
    "PRESENT": "the qualifier value and exact source span are both supplied.",
    "NOT_APPLICABLE": "the qualifier does not apply to this source-local claim.",
    "UNRESOLVED": "the qualifier may apply but cannot be resolved from the cited text.",
}
_CLAIM_ARGUMENT_ROLE = {
    "INTERVENTION": "the span is an administered, assigned, or evaluated intervention.",
    "CONDITION": "the span is the disease, disorder, phenotype, or clinical condition.",
    "POPULATION": "the span identifies the studied population or cohort.",
    "VARIANT": "the span identifies a molecular variant or biological state.",
    "OUTCOME": "the span identifies a measured or reported outcome.",
    "COMPARATOR": "the span identifies the comparison arm, exposure, or condition.",
    "TIMEFRAME": "the span identifies a source-stated duration or timepoint.",
    "STUDY_DESIGN": "the span identifies the source-stated study design.",
    "TREATMENT_SETTING": "the span identifies the clinical treatment setting.",
    "GENE_OR_PROTEIN": "the span identifies a gene or protein entity.",
    "CHEMICAL_OR_DRUG": "the span identifies a chemical or drug outside an intervention role.",
    "BIOMARKER": "the span identifies a source-stated biomarker.",
    "EXPOSURE": "the span identifies an environmental, behavioral, or clinical exposure.",
    "BIOLOGICAL_PROCESS": "the span identifies a biological process or mechanism.",
    "ANATOMY": "the span identifies an anatomical structure or location.",
    "MEASUREMENT": "the span identifies a measured quantity or assay result.",
    "OTHER_ENTITY": "the span is a material biomedical entity not covered by another role.",
}
_CLAIM_EVENT_ROLE = {
    "AGENT": "the span initiates or performs the event.",
    "THEME": "the span is acted on or undergoes the event.",
    "TARGET": "the span is the explicit target of the event.",
    "CAUSE": "the span explicitly causes or controls the event.",
    "EFFECT": "the span is the explicit result of the event.",
    "CONTEXT": "the span provides material event context.",
    "SITE": "the span identifies the event site.",
    "CSITE": "the span identifies the causal event site.",
    "ATLOC": "the span identifies the current event location.",
    "TOLOC": "the span identifies the destination location.",
    "FROMLOC": "the span identifies the origin location.",
    "MEASURE": "the span identifies the event measurement.",
}
_CLAIM_EVENT_TYPE = {
    "EXPRESSION": "the source explicitly states gene or protein expression.",
    "TRANSCRIPTION": "the source explicitly states transcription of genetic material.",
    "DEGRADATION": "the source explicitly states molecular degradation.",
    "PHOSPHORYLATION": "the source explicitly states phosphorylation.",
    "LOCALIZATION": "the source explicitly states molecular or cellular localization.",
    "BINDING": "the source explicitly states physical or molecular binding.",
    "REGULATION": "the source states regulation without a resolved direction.",
    "POSITIVE_REGULATION": "the source explicitly states positive regulation.",
    "NEGATIVE_REGULATION": "the source explicitly states negative regulation.",
    "INCREASE": "the source explicitly states an increase in a measured state or outcome.",
    "DECREASE": "the source explicitly states a decrease in a measured state or outcome.",
    "ASSOCIATION": "the source explicitly states a non-causal association.",
    "TREATMENT_RESPONSE": "the source explicitly states response to an intervention.",
    "NO_EFFECT": "the source explicitly states no effect or response.",
    "OTHER_EXPLICIT": "the source explicitly states an event not covered by another category.",
}
_FACT_SUPPORT = {
    "INSUFFICIENT": "no cited span establishes the asserted fact.",
    "TENTATIVE": "a cited span is indirect, incomplete, or explicitly uncertain.",
    "SUPPORTED": "a cited span directly establishes the asserted fact.",
    "STRONG": "multiple independent cited spans directly establish the same fact.",
}
_FACT_GROUNDING = {
    "SPAN": "the finding is anchored to one literal source span.",
    "SECTION": "the finding is anchored to a named source section but not one span.",
    "DOCUMENT": "the finding is supported only at whole-document scope.",
    "GENERATED": "the finding has no source anchor and was generated by the model.",
    "GRAPH_INFERENCE": "the finding follows from a cited graph path rather than source text.",
}
_FACT_SPECULATION = {
    "DIRECT": "the cited source states the fact without hedging.",
    "HEDGED": "the cited source explicitly hedges the fact.",
    "HYPOTHETICAL": "the cited source presents the fact as hypothetical.",
    "NOT_APPLICABLE": "speculation does not apply to this structured finding.",
}
_FACT_MAPPING = {
    "RESOLVED": "the cited entity or relation maps to one canonical identifier.",
    "AMBIGUOUS": "more than one canonical mapping remains possible.",
    "NOT_APPLICABLE": "the finding does not require canonical mapping.",
}
_GRAPH_SUPPORT = {
    "INSUFFICIENT": "no graph evidence item supports the result.",
    "TENTATIVE": "graph evidence is indirect or incomplete.",
    "SUPPORTED": "a relation or observation directly supports the result.",
    "STRONG": "multiple independent graph evidence items directly support the result.",
}
_GRAPH_GROUNDING = {
    "NONE": "the result has no entity, relation, or observation grounding.",
    "ENTITY": "the result is grounded only to a matching entity.",
    "RELATION": "the result is grounded to at least one relation.",
    "OBSERVATION": "the result is grounded to at least one observation.",
    "AGGREGATED": "the result is grounded to both relation and observation evidence.",
}
_ORCHESTRATOR_ACTION = {
    action: f"the deterministic action registry allows the {action} workflow at this checkpoint."
    for action in (
        "DERIVE_DRIVEN_TERMS",
        "ESCALATE_TO_HUMAN",
        "GENERATE_BRIEF",
        "INGEST_AND_EXTRACT_PUBMED",
        "INITIALIZE_WORKSPACE",
        "LOAD_MONDO_GROUNDING",
        "QUERY_PUBMED",
        "REVIEW_PDF_WORKSET",
        "REVIEW_TEXT_WORKSET",
        "RUN_BOOTSTRAP",
        "RUN_CHASE_ROUND",
        "RUN_GRAPH_CONNECTION",
        "RUN_GRAPH_SEARCH",
        "RUN_HGNC_GROUNDING",
        "RUN_HYPOTHESIS_GENERATION",
        "RUN_STRUCTURED_ENRICHMENT",
        "RUN_UNIPROT_GROUNDING",
        "SEARCH_DISCONFIRMING",
        "STOP",
    )
}


def _fact_categories(prefix: str) -> tuple[CategoryFieldPolicy, ...]:
    evidence = "The finding must include its source locator and supporting evidence."
    return (
        _category(
            f"{prefix}.support_band",
            _FACT_SUPPORT,
            evidence_requirement=evidence,
        ),
        _category(
            f"{prefix}.grounding_level",
            _FACT_GROUNDING,
            evidence_requirement=evidence,
        ),
        _category(
            f"{prefix}.speculation_level",
            _FACT_SPECULATION,
            evidence_requirement=evidence,
        ),
        _category(
            f"{prefix}.mapping_status",
            _FACT_MAPPING,
            evidence_requirement=evidence,
        ),
    )


def _graph_categories(prefix: str) -> tuple[CategoryFieldPolicy, ...]:
    evidence = "The category must be reproducible from the attached graph evidence IDs."
    return (
        _category(
            f"{prefix}.support_band",
            _GRAPH_SUPPORT,
            evidence_requirement=evidence,
        ),
        _category(
            f"{prefix}.grounding_level",
            _GRAPH_GROUNDING,
            evidence_requirement=evidence,
        ),
    )


_POLICIES = (
    AgentOutputSchemaPolicy(
        schema_id="evidence_selection.semantic.v2",
        schema_names=("EvidenceSelectionSemanticBatchContract",),
        shape_hash="b1428a8b75b9e6eb14bf2faddd7db7c8689bb2097c5282a7b9dfebd67744bdab",
        producer_paths=("evidence_selection/semantic/model.py",),
        prompt_identifiers=("evidence_selection.semantic_selector.v2",),
        categorical_fields=(
            _category(
                "$.schema_version",
                {
                    "evidence_selection_semantic_agent.v2": (
                        "the payload follows semantic selector schema version 2."
                    ),
                },
                evidence_requirement="This is a fixed protocol marker.",
            ),
            _category(
                "$.assessments[].decision",
                {
                    "select": "all required criteria are supported and no exclusion is triggered.",
                    "reject": "a required criterion is contradicted or an exclusion is triggered.",
                    "review": "the available source text cannot resolve a required criterion.",
                },
                evidence_requirement="Every decision must cite the complete criterion findings.",
            ),
            _category(
                "$.assessments[].objective_match",
                {
                    "direct": "the record directly answers the stated research objective.",
                    "supporting": "the record supplies evidence needed to answer the objective.",
                    "context_only": "the record supplies background but no answer evidence.",
                    "off_objective": "the record addresses a different question.",
                    "uncertain": "the supplied text cannot establish objective alignment.",
                },
                evidence_requirement="A cited title or abstract span must establish the category.",
            ),
            *(
                _category(
                    f"$.assessments[].{field_name}",
                    {
                        "match": f"the cited record explicitly satisfies {label}.",
                        "no_match": f"the cited record explicitly contradicts {label}.",
                        "not_required": f"the research objective does not require {label}.",
                        "uncertain": f"the supplied record does not resolve {label}.",
                    },
                    evidence_requirement="A literal cited span or explicit missing-information finding is required.",
                )
                for field_name, label in (
                    ("entity_variant_match", "the requested entity or variant"),
                    ("population_match", "the requested population"),
                    ("intervention_match", "the requested intervention"),
                    ("outcome_match", "the requested outcome"),
                    ("study_type_match", "the requested study type"),
                )
            ),
            _category(
                "$.assessments[].inclusion_assessment",
                {
                    "met": "every inclusion criterion has direct supporting evidence.",
                    "not_met": "at least one inclusion criterion is contradicted.",
                    "uncertain": "at least one inclusion criterion lacks enough evidence.",
                },
                evidence_requirement="Criterion-level findings and cited spans are required.",
            ),
            _category(
                "$.assessments[].exclusion_assessment",
                {
                    "not_triggered": "no exclusion criterion is supported by the cited record.",
                    "triggered": "at least one exclusion criterion is directly supported.",
                    "uncertain": "the record cannot resolve at least one applicable exclusion.",
                },
                evidence_requirement="Criterion-level findings and cited spans are required.",
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="evidence_selection.source_plan.v1",
        schema_names=("ModelEvidenceSelectionSourcePlanContract",),
        shape_hash="4b0643668ca687eafd5796f669b25d728ca7cbac352dadb7c6a7f1800a4a7780",
        producer_paths=("evidence_selection_model_planner.py",),
        prompt_identifiers=("evidence_selection.source_planner.v1",),
    ),
    AgentOutputSchemaPolicy(
        schema_id="graph_connection.agent.v1",
        schema_names=("_GraphConnectionExecutionContract",),
        shape_hash="8abaa06aefb8c10ee2b151274733f43e6795ac1e206d011e0c33dec9274c7a5d",
        producer_paths=("graph_connection_runtime.py",),
        prompt_identifiers=("graph_connection.system_and_request.v2",),
        categorical_fields=(
            _category(
                "$.decision",
                _RUN_DECISION,
                evidence_requirement="The executed path and run ID are required.",
            ),
            _category(
                "$.evidence[].source_type",
                _SOURCE_TYPE,
                evidence_requirement="Every item requires a stable locator.",
            ),
            _category(
                "$.proposed_relations[].evidence_tier",
                {
                    "COMPUTATIONAL": "the relation is model-generated and not trusted evidence."
                },
                evidence_requirement="The agent run ID is required.",
            ),
            *_fact_categories("$.proposed_relations[].assessment"),
            *_fact_categories("$.rejected_candidates[].assessment"),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="graph_search.agent.v1",
        schema_names=("_GraphSearchExecutionContract",),
        shape_hash="7015f3a669f3d7794b2d287bc6b52081e5d4f976fd9d1c061f6b2e950faaa855",
        producer_paths=("graph_search_runtime.py",),
        prompt_identifiers=("graph_search.system_and_request.v2",),
        categorical_fields=(
            _category(
                "$.decision",
                _RUN_DECISION,
                evidence_requirement="The executed path and run ID are required.",
            ),
            _category(
                "$.evidence[].source_type",
                _SOURCE_TYPE,
                evidence_requirement="Every item requires a stable locator.",
            ),
            *_graph_categories("$.assessment"),
            *_graph_categories("$.results[].assessment"),
            *_graph_categories("$.results[].evidence_chain[].assessment"),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="research_onboarding.agent.v1",
        schema_names=("OnboardingAssistantModelOutput",),
        shape_hash="0fed46693511f4f2807d37e872c2f96677f80991a3cded883d5a7fbb319a6849",
        producer_paths=("research_onboarding_agent_runtime.py",),
        prompt_identifiers=("research_onboarding.system_and_turn.v1",),
        categorical_fields=(
            _category(
                "$.evidence[].source_type",
                _SOURCE_TYPE,
                evidence_requirement="Every item requires a stable locator.",
            ),
            _category(
                "$.message_type",
                {
                    "clarification_request": "a required research input is still missing.",
                    "plan_ready": "all required onboarding inputs are present.",
                },
                evidence_requirement="The state patch and rationale must identify the condition.",
            ),
            _category(
                "$.state_patch.onboarding_status",
                {
                    "awaiting_researcher_reply": "the workflow requires a researcher response.",
                    "plan_ready": "the workflow has enough input to build the plan.",
                },
                evidence_requirement="The pending questions must establish the status.",
            ),
            _category(
                "$.state_patch.thread_status",
                {
                    "your_turn": "the researcher must answer a question.",
                    "review_needed": "the researcher must review a completed plan.",
                },
                evidence_requirement="The suggested action must establish the status.",
            ),
            _category(
                "$.suggested_actions[].action_type",
                {
                    "reply": "the next action is a researcher response.",
                    "review": "the next action is review of generated work.",
                },
                evidence_requirement="The corresponding action payload is required.",
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="pubmed.relevance.v1",
        schema_names=("PubMedRelevanceModelOutput",),
        shape_hash="edeba4193516a67036849983c26be40ce62ac17794e317d2fbc654e50c634e66",
        producer_paths=("pubmed_relevance.py",),
        prompt_identifiers=("pubmed.relevance.title_abstract.v1",),
        categorical_fields=(
            _category(
                "$.evidence[].source_type",
                _SOURCE_TYPE,
                evidence_requirement="Every item requires a stable locator.",
            ),
            _category(
                "$.relevance",
                {
                    "relevant": "the title or abstract directly addresses the supplied research context.",
                    "non_relevant": "the title and abstract do not address the supplied research context.",
                },
                evidence_requirement="A literal title or abstract span is required.",
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="relation_type_resolution.agent.v1",
        schema_names=("RelationTypeDecision",),
        shape_hash="4ae532517c388aa19610e41bbfa6ae129e11a3251a6b53a00ba671b1ba6b8f78",
        producer_paths=("relation_type_resolver.py",),
        prompt_identifiers=("relation_type_resolution.system_and_request.v1",),
        categorical_fields=(
            _category(
                "$.action",
                {
                    "map_to_existing": "one existing canonical relation has the same semantics.",
                    "register_new": "no canonical relation covers the supported semantics.",
                    "requires_review": "the available context cannot resolve the mapping safely.",
                    "typo_correction": "the input differs from one canonical relation only by a demonstrable typo.",
                },
                evidence_requirement="The rationale must cite the candidate taxonomy entries.",
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="entity_resolution.agent.v1",
        schema_names=("EntityDecision",),
        shape_hash="1f930649a4bbc34b39bd204d05073fd27db6d8b5de88c9cda5050c7ac0d3835c",
        producer_paths=("relation_type_resolver.py",),
        prompt_identifiers=("entity_resolution.system_and_request.v1",),
        categorical_fields=(
            _category(
                "$.action",
                {
                    "match_existing": "one existing entity uniquely matches the supplied label and anchors.",
                    "create_new": "no existing entity matches the supplied label and anchors.",
                },
                evidence_requirement="The rationale must cite candidate entities and supplied anchors.",
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="marrvel.gene_inference.v1",
        schema_names=("_MarrvelGeneInferenceResult",),
        shape_hash="e36df65cd58006ebeef2350b47cc09662baa1ae957e17d1001fe64a0204a7d5e",
        producer_paths=("marrvel_enrichment.py",),
        prompt_identifiers=("marrvel.gene_inference.v1",),
    ),
    AgentOutputSchemaPolicy(
        schema_id="document_extraction.claim_inventory.v3",
        schema_names=("LLMClaimInventoryResult",),
        shape_hash="116d85c696bb904f7e9f7539a048816686054839ea10e594f2ebc7f2ec75a0e2",
        producer_paths=(
            "document_extraction_support/llm_extraction/claim_inventory.py",
        ),
        prompt_identifiers=("document_extraction.claim_inventory.v9",),
        categorical_fields=(
            _category(
                "$.claims[].source_locator",
                {
                    "normalized_extraction_text": (
                        "the exact claim span comes from the frozen normalized source chunk."
                    ),
                },
                evidence_requirement=(
                    "Every inventory span and endpoint anchor must bind exactly to the source chunk."
                ),
            ),
            _category(
                "$.claims[].arguments[].role",
                _CLAIM_ARGUMENT_ROLE,
                evidence_requirement=(
                    "The exact argument span and complete assertion must establish the role."
                ),
            ),
            _category(
                "$.claims[].arguments[].event_role",
                _CLAIM_EVENT_ROLE,
                evidence_requirement=(
                    "The exact argument span and relation cue must establish the event role."
                ),
            ),
            _category(
                "$.claims[].claim_kind",
                _CLAIM_KIND,
                evidence_requirement=(
                    "The exact inventory span must establish whether the item is a finding, hypothesis, procedure, measurement, or ambiguous."
                ),
            ),
            _category(
                "$.claims[].event_type",
                _CLAIM_EVENT_TYPE,
                evidence_requirement=(
                    "The exact inventory span and relation cue must establish the event category."
                ),
            ),
            _category(
                "$.claims[].polarity",
                _INVENTORY_POLARITY,
                evidence_requirement=(
                    "The exact inventory span must establish the claim direction."
                ),
            ),
            _category(
                "$.claims[].epistemic_status",
                _INVENTORY_EPISTEMIC_STATUS,
                evidence_requirement=(
                    "The exact inventory span must establish the statement status."
                ),
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="document_extraction.claim_inventory_completeness.v3",
        schema_names=("ClaimInventoryCompletenessReview",),
        shape_hash="d7aacf725be8407731706a9fc24d456c339076be1638a3728afb5fd079b6641b",
        producer_paths=(
            "document_extraction_support/llm_extraction/claim_inventory.py",
        ),
        prompt_identifiers=("document_extraction.claim_inventory_completeness.v8",),
        categorical_fields=(
            _category(
                "$.decision",
                {
                    "COMPLETE": "every explicit source-local claim is represented in the supplied inventory.",
                    "INCOMPLETE": "at least one explicit source-local claim is absent from the supplied inventory.",
                },
                evidence_requirement=(
                    "The decision must compare the complete returned inventory with the frozen source chunk."
                ),
            ),
            _category(
                "$.missing_claims[].source_locator",
                {
                    "normalized_extraction_text": (
                        "the missing claim descriptor binds to the frozen normalized source chunk."
                    ),
                },
                evidence_requirement="Every missing claim span must bind exactly to source.",
            ),
            _category(
                "$.missing_claims[].arguments[].role",
                _CLAIM_ARGUMENT_ROLE,
                evidence_requirement="The missing claim span must establish every argument role.",
            ),
            _category(
                "$.missing_claims[].arguments[].event_role",
                _CLAIM_EVENT_ROLE,
                evidence_requirement="The missing claim span must establish every event role.",
            ),
            _category(
                "$.missing_claims[].claim_kind",
                _CLAIM_KIND,
                evidence_requirement="The missing descriptor must be a relation-eligible scientific kind.",
            ),
            _category(
                "$.missing_claims[].event_type",
                _CLAIM_EVENT_TYPE,
                evidence_requirement="The missing claim span must establish the event category.",
            ),
            _category(
                "$.missing_claims[].polarity",
                _INVENTORY_POLARITY,
                evidence_requirement="The missing claim span must establish direction.",
            ),
            _category(
                "$.missing_claims[].epistemic_status",
                _INVENTORY_EPISTEMIC_STATUS,
                evidence_requirement="The missing claim span must establish status.",
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="document_extraction.claim_inventory_recovery.v4",
        schema_names=("MissingClaimRecoveryDecision",),
        shape_hash="a97e2bcfe7ac51a317407f5e59f5ba66bbd575546fe491ebc4dbf51cd220d33f",
        producer_paths=(
            "document_extraction_support/llm_extraction/claim_inventory.py",
        ),
        prompt_identifiers=("document_extraction.claim_inventory_recovery.v8",),
        categorical_fields=(
            _category(
                "$.decision",
                {
                    "RECOVER_EXPLICIT_CLAIM": "the reviewed descriptor is an explicit source-supported biomedical claim.",
                    "EXCLUDE_PROCEDURAL_METHOD": "the reviewed descriptor is procedural metadata without a biomedical relationship or result.",
                    "EXCLUDE_NOT_EXPLICIT": "the reviewed descriptor adds meaning not explicit in the frozen source.",
                    "ABSTAIN": "the source does not support a safe categorical adjudication.",
                },
                evidence_requirement=(
                    "The decision must use only the frozen source and the reviewed source-bound descriptor."
                ),
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="document_extraction.claim_framing.v2",
        schema_names=("LLMSingleClaimFramingResult",),
        shape_hash="79f83b484546c7f14f337684943fd1cd46c5d65656a481f4ba78d5b7cd9a84db",
        producer_paths=("document_extraction_support/llm_extraction/claim_framing.py",),
        prompt_identifiers=("document_extraction.claim_framing.v7",),
        numeric_fields=(
            NumericFieldPolicy(
                path="$.relations[].source_measurements[].value",
                origin=NumericOrigin.SOURCE_MEASUREMENT,
            ),
        ),
        categorical_fields=(
            _category(
                "$.decision",
                {
                    "SINGLE_FRAME": "the assertion supports exactly one complete source-bound frame.",
                    "MULTIPLE_VALID_FRAMES": "the assertion independently supports multiple graph projections.",
                    "AMBIGUOUS": "multiple source-bound frames remain plausible without a resolved choice.",
                    "ABSTAIN": "the source-bound inventory item cannot be framed without guessing.",
                },
                evidence_requirement=(
                    "The decision must be reproducible from the exact inventory span and anchors."
                ),
            ),
            _category(
                "$.abstention_reason",
                {
                    "INVENTORY_NOT_EXPLICIT": "the frozen source does not explicitly state the inventoried claim.",
                    "ENDPOINTS_AMBIGUOUS": "the source does not resolve the two semantic endpoints.",
                    "RELATION_AMBIGUOUS": "the source does not resolve a relation without invented meaning.",
                    "SOURCE_CONFLICT": "the frozen source contradicts the supplied inventory fields.",
                },
                evidence_requirement=(
                    "ABSTAIN requires a source-specific rationale tied to the exact span."
                ),
            ),
            _category(
                "$.relations[].review_status",
                {
                    "candidate": "the exact source span directly supports a canonical relation candidate.",
                    "review_only": "the exact source span is non-positive, weak, or requires review.",
                },
                evidence_requirement="The literal source span is required.",
            ),
            _category(
                "$.relations[].polarity",
                _CLAIM_POLARITY,
                evidence_requirement=(
                    "The relation polarity must equal the source-bound inventory polarity."
                ),
            ),
            _category(
                "$.relations[].epistemic_status",
                _CLAIM_EPISTEMIC_STATUS,
                evidence_requirement=(
                    "The relation status must equal the source-bound inventory status."
                ),
            ),
            _category(
                "$.relations[].source_measurements[].field_name",
                {
                    "THRESHOLD": "the number defines a source-stated cutoff or boundary.",
                    "TIMEFRAME": "the number defines a source-stated duration or timepoint.",
                    "OUTCOME": "the number is a source-stated result or outcome measurement.",
                    "DOSAGE": "the number is a source-stated administered dose.",
                    "POPULATION_SIZE": "the number is a source-stated participant or sample count.",
                    "OTHER": "the source-stated number has none of the other closed roles.",
                },
                evidence_requirement=(
                    "The exact numeric literal and complete source span are required."
                ),
            ),
            _category(
                "$.relations[].source_measurements[].extraction_method",
                {
                    "agent_exact_copy": (
                        "the agent copied the exact ASCII numeric literal from the claim span."
                    ),
                },
                evidence_requirement=(
                    "The literal must occur inside the exact claim evidence span."
                ),
            ),
            *(
                _category(
                    f"$.relations[].{field}.state",
                    _CLAIM_QUALIFIER_STATE,
                    evidence_requirement=(
                        "PRESENT requires a literal value and exact source span; "
                        "absence must be explicit."
                    ),
                )
                for field in (
                    "biological_or_variant_state",
                    "condition",
                    "population",
                    "intervention",
                    "comparator",
                    "outcome",
                    "study_design",
                    "treatment_setting",
                    "timeframe",
                    "threshold",
                )
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="document_extraction.relation.v3",
        schema_names=("LLMExtractionResult",),
        shape_hash="b4027c5eae4151e644bbfc057b89a9aa166ffdaeeded22b77b97a6f81891330a",
        producer_paths=("document_extraction_support/llm_fulltext_extraction.py",),
        prompt_identifiers=("document_extraction.relation.v3",),
        numeric_fields=(
            NumericFieldPolicy(
                path="$.relations[].source_measurements[].value",
                origin=NumericOrigin.SOURCE_MEASUREMENT,
            ),
        ),
        categorical_fields=(
            _category(
                "$.relations[].review_status",
                {
                    "candidate": "the cited sentence directly supports a canonical relation candidate.",
                    "review_only": "the cited sentence is weak, hedged, or requires human interpretation.",
                },
                evidence_requirement="The literal source sentence is required.",
            ),
            _category(
                "$.relations[].polarity",
                _CLAIM_POLARITY,
                evidence_requirement=(
                    "The literal source sentence must establish the direction."
                ),
            ),
            _category(
                "$.relations[].epistemic_status",
                _CLAIM_EPISTEMIC_STATUS,
                evidence_requirement=(
                    "The literal source sentence must establish the statement status."
                ),
            ),
            _category(
                "$.relations[].source_measurements[].field_name",
                {
                    "THRESHOLD": "the number defines a source-stated cutoff or boundary.",
                    "TIMEFRAME": "the number defines a source-stated duration or timepoint.",
                    "OUTCOME": "the number is a source-stated result or outcome measurement.",
                    "DOSAGE": "the number is a source-stated administered dose.",
                    "POPULATION_SIZE": "the number is a source-stated participant or sample count.",
                    "OTHER": "the source-stated number has none of the other closed measurement roles.",
                },
                evidence_requirement=(
                    "The exact numeric literal and its complete source span are required."
                ),
            ),
            _category(
                "$.relations[].source_measurements[].extraction_method",
                {
                    "agent_exact_copy": (
                        "the model copied the exact ASCII numeric literal from the cited claim span."
                    ),
                },
                evidence_requirement=(
                    "The literal span must be inside the exact claim evidence span."
                ),
            ),
            *(
                _category(
                    f"$.relations[].{field}.state",
                    _CLAIM_QUALIFIER_STATE,
                    evidence_requirement=(
                        "PRESENT requires a literal value and exact source span; "
                        "absence must be explicit."
                    ),
                )
                for field in (
                    "biological_or_variant_state",
                    "condition",
                    "population",
                    "intervention",
                    "comparator",
                    "outcome",
                    "study_design",
                    "treatment_setting",
                    "timeframe",
                    "threshold",
                )
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="document_extraction.proposal_review.v1",
        schema_names=("ProposalReviewResult",),
        shape_hash="172c1f2ab7a2a8d6f3b47dfab1fe2a50a185aac1460b30adb27a4fea22058247",
        producer_paths=("document_extraction.py",),
        prompt_identifiers=("document_extraction.proposal_review.v1",),
        categorical_fields=(
            _category(
                "$.reviews[].factual_support",
                {
                    "strong": "multiple direct source spans support the proposal.",
                    "moderate": "one direct source span supports the proposal.",
                    "tentative": "the source is hedged or indirect.",
                    "unsupported": "no cited source span supports the proposal.",
                },
                evidence_requirement="A factual rationale tied to source text is required.",
            ),
            _category(
                "$.reviews[].goal_relevance",
                {
                    "direct": "the proposal directly answers the research goal.",
                    "supporting": "the proposal supports an answer to the goal.",
                    "peripheral": "the proposal is related background only.",
                    "off_target": "the proposal addresses a different goal.",
                    "unscoped": "the supplied goal is insufficient to classify relevance.",
                },
                evidence_requirement="A relevance rationale tied to the goal is required.",
            ),
            _category(
                "$.reviews[].priority",
                {
                    "prioritize": "direct supported evidence requires immediate review.",
                    "review": "supported evidence should enter normal review.",
                    "background": "the proposal is context only.",
                    "ignore": "the proposal is unsupported or off target.",
                },
                evidence_requirement="The factual-support and goal-relevance categories must deterministically permit this value.",
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="model_health.probe.v1",
        schema_names=("_ProbeOutput",),
        shape_hash="53ceee97278087ef366f8a0a8399cfab1b60ca83917bf20b3e1063310fe9fce4",
        producer_paths=("runtime/model_health.py", "runtime_support.py"),
        prompt_identifiers=("model_health.probe.v1",),
        categorical_fields=(
            _category(
                "$.status",
                {"ok": "the provider returned the exact structured health response."},
                evidence_requirement="This is a fixed transport-health protocol marker.",
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="variant_extraction.agent.v1",
        schema_names=("LLMExtractionContract",),
        shape_hash="6fa90f3c8d685e7829ad3ec44a89f5e435f525e1e77938fead762ed1a3ca65e4",
        producer_paths=("variant_extraction_bridges.py",),
        prompt_identifiers=("variant_extraction.context.v9",),
        numeric_fields=(
            NumericFieldPolicy(
                path="$.observations[].value.value",
                origin=NumericOrigin.SOURCE_MEASUREMENT,
            ),
        ),
        categorical_fields=(
            _category(
                "$.decision",
                _RUN_DECISION,
                evidence_requirement="The executed path and run ID are required.",
            ),
            _category(
                "$.evidence[].source_type",
                _SOURCE_TYPE,
                evidence_requirement="Every item requires a stable locator.",
            ),
            _category(
                "$.rejected_facts[].fact_type",
                {
                    "observation": "the rejected candidate is an observation.",
                    "relation": "the rejected candidate is a relation.",
                },
                evidence_requirement="The rejected payload and reason are required.",
            ),
            _category(
                "$.relations[].polarity",
                {
                    "SUPPORT": "the cited source supports the relation.",
                    "REFUTE": "the cited source contradicts the relation.",
                    "UNCERTAIN": "the cited source is ambiguous or hedged.",
                    "HYPOTHESIS": "the cited source presents the relation as hypothetical.",
                },
                evidence_requirement="A literal evidence span and locator are required.",
            ),
            *(
                category
                for prefix in (
                    "$.entities[].assessment",
                    "$.observations[].assessment",
                    "$.relations[].assessment",
                    "$.rejected_facts[].assessment",
                )
                for category in _fact_categories(prefix)
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="full_ai.shadow_planner.v1",
        schema_names=(
            "ShadowPlannerLiveRecommendationOutput",
            "ShadowPlannerRecommendationOutput",
        ),
        shape_hash="fd01368f0ece1492b7ab09d5db7188e82268c319729e83473339c576a98256dc",
        producer_paths=("full_ai_orchestrator/shadow_planner/runtime.py",),
        prompt_identifiers=("full_ai.shadow_planner.prompt.v1",),
        categorical_fields=(
            _category(
                "$.action_type",
                _ORCHESTRATOR_ACTION,
                evidence_requirement=(
                    "The action must be present in the deterministic checkpoint action registry."
                ),
                allow_schema_subset=True,
            ),
            _category(
                "$.benefit_findings[].kind",
                {
                    "closes_evidence_gap": "the cited workspace state identifies a specific unresolved evidence gap this action addresses.",
                    "resolves_pending_question": "the cited workspace state identifies a pending question this action can address.",
                    "adds_objective_relevant_evidence": "the action gathers evidence directly tied to the stated objective.",
                    "corroborates_existing_evidence": "the action tests or independently supports an existing finding.",
                    "enables_synthesis": "the cited workspace state shows this action completes a prerequisite for synthesis.",
                    "no_material_benefit": "the cited workspace state shows continuing adds no material evidence or workflow benefit.",
                },
                evidence_requirement="Every benefit finding requires its own workspace-grounded evidence statement.",
            ),
            _category(
                "$.risk_findings[].kind",
                {
                    "external_side_effect": "the action can change state outside the shadow-planner decision artifact.",
                    "irreversible_action": "the action can create a state change that the workflow cannot automatically undo.",
                    "sensitive_data_exposure": "the action can disclose protected or sensitive data beyond its current boundary.",
                    "requires_human_judgment": "the workspace identifies a semantic or governance decision reserved for a human.",
                    "uncertain_cost": "the workspace lacks enough information to bound the action cost under policy.",
                    "no_material_risk": "the cited workspace state identifies none of the registered material risks.",
                },
                evidence_requirement="Every risk finding requires its own workspace-grounded evidence statement.",
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="research.brief.v1",
        schema_names=("LLMBriefOutput",),
        shape_hash="9c7621ed9f2066c3bc01806be1f8946caff0dcb1c6445db460431d91a8e5c019",
        producer_paths=("research_init_brief.py",),
        prompt_identifiers=("research.llm_brief_synthesis.v1",),
    ),
)

AGENT_OUTPUT_SCHEMA_REGISTRY = AgentOutputSchemaRegistry(_POLICIES)


def validate_registered_agent_output_schema(
    *,
    schema_id: str,
    output_schema: type[object],
) -> AgentOutputSchemaPolicy:
    """Validate a production model-output boundary against the registry."""

    return AGENT_OUTPUT_SCHEMA_REGISTRY.validate(
        schema_id=schema_id,
        output_schema=output_schema,
    )


__all__ = [
    "AGENT_OUTPUT_SCHEMA_REGISTRY",
    "validate_registered_agent_output_schema",
]
