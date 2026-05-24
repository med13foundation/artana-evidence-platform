"""Ontology-normalized convergence queries for research-init evidence."""

from .contracts import (
    ConvergenceProvenance,
    ConvergenceProvenanceFilter,
    ConvergenceSpecificity,
    OntologyConvergenceClaimResponse,
    OntologyConvergenceNodeResponse,
    OntologyConvergenceQueryRequest,
    OntologyConvergenceQueryResponse,
)
from .runtime import run_ontology_convergence_query

__all__ = [
    "ConvergenceProvenance",
    "ConvergenceProvenanceFilter",
    "ConvergenceSpecificity",
    "OntologyConvergenceClaimResponse",
    "OntologyConvergenceNodeResponse",
    "OntologyConvergenceQueryRequest",
    "OntologyConvergenceQueryResponse",
    "run_ontology_convergence_query",
]
