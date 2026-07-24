"""Agent-output governance policies for bounded claim verification."""

from __future__ import annotations

from collections.abc import Mapping

from artana_evidence_api.runtime.agent_output_schema import (
    AgentOutputSchemaPolicy,
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
) -> CategoryFieldPolicy:
    return CategoryFieldPolicy(
        path=path,
        values=tuple(
            CategoryValuePolicy(
                value=value,
                definition=definition,
                positive_example=f"Use {value!r} only when {definition}",
                counterexample=(
                    f"Do not use {value!r} when that observable condition is absent."
                ),
            )
            for value, definition in definitions.items()
        ),
        evidence_requirement=evidence_requirement,
        invalid_behavior="Reject the model output and record an invalid response.",
    )


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
_QUALIFIER_STATE = {
    "PRESENT": "the qualifier value and exact source span are both supplied.",
    "NOT_APPLICABLE": "the qualifier does not apply to this source-local claim.",
    "UNRESOLVED": "the qualifier may apply but cannot be resolved from the cited text.",
}
_VERDICT = {
    "ENTAILED": "the complete structured claim is directly supported by the claim-local source.",
    "CONTRADICTED": "the claim-local source directly conflicts with the structured claim.",
    "INSUFFICIENT": "the claim-local source does not establish the complete structured claim.",
    "ABSTAIN": "the verifier cannot safely choose another verdict from the claim-local source.",
}
_APPLICABILITY = {
    "FAITHFUL": "the semantic axis is present and faithfully represented by the claim.",
    "INCORRECT": "the semantic axis is present but incorrectly represented by the claim.",
    "NOT_APPLICABLE": "the semantic axis does not apply to this source-local claim.",
}
_BINARY = {
    "FAITHFUL": "the semantic axis is faithfully represented by the claim.",
    "INCORRECT": "the semantic axis is incorrectly represented by the claim.",
}


CLAIM_VERIFICATION_AGENT_OUTPUT_POLICIES = (
    AgentOutputSchemaPolicy(
        schema_id="document_extraction.claim_falsification.v1",
        schema_names=("ClaimVerificationOutput",),
        shape_hash="f50ddb40450841ac3092d8319e001f6f15bcde3128c9a7c06dd79e23dccb1c7a",
        producer_paths=(
            "document_extraction_support/llm_extraction/claim_falsification.py",
        ),
        prompt_identifiers=("document_extraction.claim_falsification.v1",),
        categorical_fields=(
            _category(
                "$.verdict",
                _VERDICT,
                evidence_requirement="Exact claim-local evidence must establish the complete verdict.",
            ),
            _category(
                "$.participant_roles",
                {
                    "FAITHFUL": "every participant has the source-supported event role.",
                    "INCORRECT": "at least one participant has a wrong or merged event role.",
                    "AMBIGUOUS": "the source cannot resolve a material participant role.",
                },
                evidence_requirement="Exact participant and event spans must establish each role.",
            ),
            *(
                _category(
                    path,
                    _APPLICABILITY,
                    evidence_requirement="Exact evidence must establish the axis and applicability.",
                )
                for path in (
                    "$.direction",
                    "$.comparison",
                    "$.statistical_interpretation",
                )
            ),
            *(
                _category(
                    path,
                    _BINARY,
                    evidence_requirement="Exact claim-local evidence must establish the axis.",
                )
                for path in ("$.polarity", "$.uncertainty")
            ),
            _category(
                "$.observed_statistical_evidence",
                {
                    "P_VALUE": "the source reports an exact p-value observation.",
                    "CONFIDENCE_INTERVAL": "the source reports an exact confidence interval.",
                    "EFFECT_ESTIMATE": "the source reports an exact effect estimate.",
                    "NONE": "the source reports no statistical observation for this claim.",
                },
                evidence_requirement="The exact statistical evidence span is required.",
            ),
            _category(
                "$.author_statistical_claim",
                {
                    "SIGNIFICANT": "the authors explicitly claim statistical significance.",
                    "NOT_SIGNIFICANT": "the authors explicitly claim no statistical significance.",
                    "NOT_CLAIMED": "the source makes neither explicit author interpretation.",
                },
                evidence_requirement="Interpretation requires explicit author language.",
            ),
            _category(
                "$.completeness",
                {
                    "COMPLETE": "the claim preserves every material event component in scope.",
                    "INCOMPLETE": "the claim omits a material event component.",
                    "AMBIGUOUS": "the source cannot resolve whether the claim is complete.",
                },
                evidence_requirement="The complete claim-local event passage is required.",
            ),
            _category(
                "$.failure_axes[]",
                {
                    "PARTICIPANT_ROLES": "event participant roles are wrong or unresolved.",
                    "DIRECTION": "the claim misstates event direction.",
                    "COMPARISON": "the claim misstates a source comparison.",
                    "POLARITY": "the claim misstates positive, negative, or null polarity.",
                    "UNCERTAINTY": "the claim misstates uncertainty or epistemic status.",
                    "STATISTICAL_INTERPRETATION": "the claim misstates statistics or interpretation.",
                    "MODIFIER": "the claim omits or misstates a source modifier.",
                    "CORE_EVENT": "the relation or event identity is wrong.",
                    "PRIMARY_PARTICIPANT": "a required primary participant is absent or wrong.",
                    "UNSUPPORTED_EVIDENCE": "the claim depends on absent evidence.",
                    "AMBIGUOUS_SOURCE_SCOPE": "the source scope cannot support one claim.",
                    "NEW_EVENT_REQUIRED": "completeness requires discovery of another event.",
                },
                evidence_requirement="Every failure axis requires exact claim-local evidence.",
            ),
        ),
    ),
    AgentOutputSchemaPolicy(
        schema_id="document_extraction.claim_repair.v1",
        schema_names=("ClaimSemanticPatch",),
        shape_hash="b43a68e382e1ee59123c9e170617cd3fb5a9a1d2a3fcbe694bd007fa023f95ab",
        producer_paths=(
            "document_extraction_support/llm_extraction/claim_repair.py",
        ),
        prompt_identifiers=("document_extraction.claim_repair.v1",),
        numeric_fields=(
            NumericFieldPolicy(
                path="$.source_measurements[].value",
                origin=NumericOrigin.SOURCE_MEASUREMENT,
            ),
        ),
        categorical_fields=(
            _category(
                "$.polarity",
                _CLAIM_POLARITY,
                evidence_requirement="Polarity repair requires exact evidence.",
            ),
            _category(
                "$.epistemic_status",
                _CLAIM_EPISTEMIC_STATUS,
                evidence_requirement="Uncertainty repair requires exact evidence.",
            ),
            _category(
                "$.assertion_arguments[].role",
                _CLAIM_ARGUMENT_ROLE,
                evidence_requirement="Role repair requires an exact existing participant.",
            ),
            _category(
                "$.assertion_arguments[].event_role",
                _CLAIM_EVENT_ROLE,
                evidence_requirement="Event-role repair requires exact trigger evidence.",
            ),
            _category(
                "$.source_measurements[].field_name",
                {
                    "THRESHOLD": "the number is a source-stated cutoff.",
                    "TIMEFRAME": "the number is a source-stated duration or timepoint.",
                    "OUTCOME": "the number is a source-stated outcome measurement.",
                    "DOSAGE": "the number is a source-stated administered dose.",
                    "POPULATION_SIZE": "the number is a source-stated sample count.",
                    "OTHER": "the number has none of the other closed roles.",
                },
                evidence_requirement="The exact numeric literal is required.",
            ),
            _category(
                "$.source_measurements[].extraction_method",
                {"agent_exact_copy": "the agent copied the exact numeric literal."},
                evidence_requirement="The literal must occur in claim-local source.",
            ),
            _category(
                "$.qualifier_updates[].value.state",
                _QUALIFIER_STATE,
                evidence_requirement="PRESENT requires an exact source-supported qualifier.",
            ),
        ),
    ),
)


__all__ = ["CLAIM_VERIFICATION_AGENT_OUTPUT_POLICIES"]
