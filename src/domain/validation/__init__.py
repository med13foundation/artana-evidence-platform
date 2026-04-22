"""
Domain validation framework for Artana Resource Library.

Provides comprehensive validation rules, quality gates, and reporting
systems to ensure data quality throughout the ETL pipeline.

Components:
- Rules: Advanced business logic validation rules
- Gates: Quality gate orchestration and checkpoints
- Reporting: Error reporting, metrics, and dashboards
"""

from .gates import (
    GateResult,
    QualityGate,
    QualityGateOrchestrator,
    ValidationPipeline,
)
from .reporting import (
    ErrorReporter,
    MetricsCollector,
    ValidationDashboard,
    ValidationReport,
)
from .rules import (
    DataQualityValidator,
    GeneValidationRules,
    PhenotypeValidationRules,
    PublicationValidationRules,
    RelationshipValidationRules,
    ValidationRule,
    ValidationRuleEngine,
    VariantValidationRules,
)

__all__ = [
    # Rules
    "ValidationRule",
    "DataQualityValidator",
    "GeneValidationRules",
    "VariantValidationRules",
    "PhenotypeValidationRules",
    "PublicationValidationRules",
    "RelationshipValidationRules",
    "ValidationRuleEngine",
    # Gates
    "QualityGate",
    "ValidationPipeline",
    "GateResult",
    "QualityGateOrchestrator",
    # Reporting
    "ValidationReport",
    "ErrorReporter",
    "MetricsCollector",
    "ValidationDashboard",
]
