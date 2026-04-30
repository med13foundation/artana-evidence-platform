"""Builtin claim qualifier seed data."""

from __future__ import annotations

from artana_evidence_db.graph_domain_types import BuiltinQualifierDefinition

GRAPH_SERVICE_BUILTIN_QUALIFIER_DEFINITIONS = (
    # --- Scoping qualifiers (contribute to canonicalization key) ---
    BuiltinQualifierDefinition(
        variable_id="QUAL_POPULATION",
        canonical_name="population",
        display_name="Population",
        data_type="STRING",
        description="Ancestry or population context, e.g. European, East Asian.",
        is_scoping=True,
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_ORGANISM",
        canonical_name="organism",
        display_name="Organism",
        data_type="STRING",
        description="Source organism, e.g. human, mouse, zebrafish.",
        is_scoping=True,
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_DEVELOPMENTAL_STAGE",
        canonical_name="developmental_stage",
        display_name="Developmental Stage",
        data_type="STRING",
        description="Developmental timing, e.g. E14.5, postnatal, adult.",
        is_scoping=True,
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_SEX",
        canonical_name="sex",
        display_name="Sex",
        data_type="STRING",
        description="Sex-specific context, e.g. male, female.",
        is_scoping=True,
    ),
    # --- Descriptive qualifiers (stored as attributes, don't split relations) ---
    BuiltinQualifierDefinition(
        variable_id="QUAL_PENETRANCE",
        canonical_name="penetrance",
        display_name="Penetrance",
        data_type="FLOAT",
        description="Proportion of carriers who express the phenotype.",
        constraints={"min": 0.0, "max": 1.0},
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_FREQUENCY",
        canonical_name="frequency",
        display_name="Allele Frequency",
        data_type="FLOAT",
        description="Allele frequency in population.",
        constraints={"min": 0.0, "max": 1.0},
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_ODDS_RATIO",
        canonical_name="odds_ratio",
        display_name="Odds Ratio",
        data_type="FLOAT",
        description="Effect size for association studies.",
        constraints={"min": 0.0},
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_P_VALUE",
        canonical_name="p_value",
        display_name="P-value",
        data_type="FLOAT",
        description="Statistical significance.",
        constraints={"min": 0.0, "max": 1.0},
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_EFFECT_SIZE",
        canonical_name="effect_size",
        display_name="Effect Size",
        data_type="FLOAT",
        description="Generic effect magnitude (beta, Cohen's d, etc.).",
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_SAMPLE_SIZE",
        canonical_name="sample_size",
        display_name="Sample Size",
        data_type="INTEGER",
        description="Number of individuals or samples in the study.",
        constraints={"min": 1},
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_POLARITY",
        canonical_name="polarity",
        display_name="Polarity",
        data_type="STRING",
        description="Participant-level polarity alias: SUPPORT, REFUTE, UNCERTAIN, HYPOTHESIS.",
    ),
)


