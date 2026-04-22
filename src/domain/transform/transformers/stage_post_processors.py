"""Post-processing stage runners split from stage_handlers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from src.domain.transform.transformers.stage_models import (
    ExportReport,
    MappedDataBundle,
    NormalizedDataBundle,
    TransformationResult,
    TransformationStage,
    TransformationStatus,
    ValidationSummary,
)


class ValidationStageRunner:
    """Validate mapped relationships to ensure structural quality."""

    def run(
        self,
        mapped_data: MappedDataBundle,
    ) -> tuple[ValidationSummary, TransformationResult]:
        start_time = time.time()
        summary = ValidationSummary()

        gene_mapper = mapped_data.gene_variant_mapper
        if gene_mapper:
            for gene_link in mapped_data.gene_variant_links:
                issues = gene_mapper.validate_mapping(gene_link)
                if issues:
                    summary.record_failure(issues)
                else:
                    summary.record_success()

        variant_mapper = mapped_data.variant_phenotype_mapper
        if variant_mapper:
            for variant_link in mapped_data.variant_phenotype_links:
                issues = variant_mapper.validate_mapping(variant_link)
                if issues:
                    summary.record_failure(issues)
                else:
                    summary.record_success()

        result = TransformationResult(
            stage=TransformationStage.VALIDATION,
            status=(
                TransformationStatus.COMPLETED
                if summary.failed == 0
                else TransformationStatus.PARTIAL
            ),
            records_processed=summary.passed + summary.failed,
            records_failed=summary.failed,
            data=summary.as_dict(),
            errors=list(summary.errors),
            duration_seconds=time.time() - start_time,
            timestamp=time.time(),
        )
        return summary, result


@dataclass
class ExportStageRunner:
    """Export normalized entities and mapping summaries to disk."""

    output_dir: Path

    def run(
        self,
        normalized_data: NormalizedDataBundle,
        mapped_data: MappedDataBundle,
    ) -> tuple[ExportReport, TransformationResult]:
        start_time = time.time()
        report = ExportReport()

        try:
            for entity_type, entities in normalized_data.as_dict().items():
                if not isinstance(entities, list) or not entities:
                    continue
                filename = f"{entity_type}_normalized.json"
                filepath = self.output_dir / filename
                serializable_entities = [
                    {
                        "primary_id": entity.primary_id,
                        "display_name": getattr(
                            entity,
                            "name",
                            getattr(entity, "symbol", None),
                        ),
                        "source": getattr(entity, "source", "unknown"),
                        "confidence_score": getattr(entity, "confidence_score", None),
                    }
                    for entity in entities
                ]
                with filepath.open("w", encoding="utf-8") as handle:
                    json.dump(serializable_entities, handle, indent=2, default=str)
                report.files_created.append(str(filepath))

            mapping_summary = {
                "gene_variant_count": len(mapped_data.gene_variant_links),
                "variant_phenotype_count": len(mapped_data.variant_phenotype_links),
                "networks_count": len(mapped_data.networks),
            }
            mappings_file = self.output_dir / "entity_mappings.json"
            with mappings_file.open("w", encoding="utf-8") as handle:
                json.dump(mapping_summary, handle, indent=2)
            report.files_created.append(str(mappings_file))

        except Exception as exc:  # pragma: no cover - defensive
            report.errors.append(f"Export failed: {exc}")

        result = TransformationResult(
            stage=TransformationStage.EXPORT,
            status=(
                TransformationStatus.COMPLETED
                if not report.errors
                else TransformationStatus.FAILED
            ),
            records_processed=len(report.files_created),
            records_failed=len(report.errors),
            data=report.as_dict(),
            errors=list(report.errors),
            duration_seconds=time.time() - start_time,
            timestamp=time.time(),
        )
        return report, result
