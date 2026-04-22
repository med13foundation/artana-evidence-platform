"""Small validation report generator used by the integration tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.type_definitions.common import JSONObject, JSONValue
from src.type_definitions.json_utils import to_json_value

from .dashboard import ValidationDashboard
from .error_reporting import ErrorReporter, ErrorSummary
from .metrics import MetricsCollector


@dataclass
class ValidationReport:
    report_id: str
    title: str
    generated_at: datetime
    time_range_hours: int
    executive_summary: JSONObject
    detailed_findings: JSONObject
    recommendations: list[str]
    data_quality_score: float
    system_health_score: float
    appendices: JSONObject


class ValidationReportGenerator:
    def __init__(
        self,
        error_reporter: ErrorReporter,
        metrics_collector: MetricsCollector,
        dashboard: ValidationDashboard,
    ) -> None:
        self._errors = error_reporter
        self._metrics = metrics_collector
        self._dashboard = dashboard
        self._counter = 0

    def generate_executive_report(
        self,
        time_range_hours: int = 168,
    ) -> ValidationReport:
        dashboard_data = self._dashboard.get_dashboard_data(force_refresh=True)
        quality_report = self._metrics.get_performance_report(time_range_hours)
        error_summary = self._errors.get_error_summary(
            time_range_hours=time_range_hours,
        )

        quality_score_metric = self._extract_performance_metric(
            quality_report,
            "quality_score",
        )
        executive_summary: JSONObject = {
            "system_health": dashboard_data.system_health,
            "quality_score": quality_score_metric,
            "total_errors": error_summary.total_errors,
        }

        alerts_json = self._json_list(dashboard_data.alerts)

        detailed_findings: JSONObject = {
            "performance_metrics": dashboard_data.performance_metrics,
            "quality_metrics": dashboard_data.quality_metrics,
            "alerts": alerts_json,
        }

        recommendations = self._build_recommendations(error_summary)

        error_summary_json = to_json_value(error_summary)
        if not isinstance(error_summary_json, dict):
            msg = "Error summary must serialize to a JSON object"
            raise TypeError(msg)
        appendices: JSONObject = {
            "error_summary": error_summary_json,
            "performance_report": quality_report,
        }

        return ValidationReport(
            report_id=self._next_id("exec"),
            title="Executive Validation Report",
            generated_at=datetime.now(UTC),
            time_range_hours=time_range_hours,
            executive_summary=executive_summary,
            detailed_findings=detailed_findings,
            recommendations=recommendations,
            data_quality_score=self._average_quality_score(
                dashboard_data.quality_metrics,
            ),
            system_health_score=dashboard_data.system_health,
            appendices=appendices,
        )

    def generate_technical_report(self, time_range_hours: int = 24) -> ValidationReport:
        dashboard_data = self._dashboard.get_dashboard_data(force_refresh=True)
        error_trends = self._errors.get_error_trends(time_range_hours)
        performance_report = self._metrics.get_performance_report(time_range_hours)

        error_trends_json = self._json_list(error_trends)
        alerts_json = self._json_list(dashboard_data.alerts)

        executive_summary: JSONObject = {
            "system_health": dashboard_data.system_health,
            "recent_alerts": alerts_json,
        }

        detailed_findings: JSONObject = {
            "error_trends": error_trends_json,
            "performance_metrics": dashboard_data.performance_metrics,
            "quality_metrics": dashboard_data.quality_metrics,
        }

        recommendations = self._build_recommendations(self._errors.get_error_summary())

        appendices: JSONObject = {
            "performance_report": performance_report,
            "alerts": alerts_json,
        }

        return ValidationReport(
            report_id=self._next_id("tech"),
            title="Technical Validation Report",
            generated_at=datetime.now(UTC),
            time_range_hours=time_range_hours,
            executive_summary=executive_summary,
            detailed_findings=detailed_findings,
            recommendations=recommendations,
            data_quality_score=self._average_quality_score(
                dashboard_data.quality_metrics,
            ),
            system_health_score=dashboard_data.system_health,
            appendices=appendices,
        )

    def export_report(
        self,
        report: ValidationReport,
        path: str,
        output_format: str = "json",
    ) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        serialized = to_json_value(report)
        if not isinstance(serialized, dict):
            msg = "ValidationReport serialised to a non-object payload"
            raise TypeError(msg)
        payload: JSONObject = serialized

        if output_format.lower() == "json":
            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return

        if output_format.lower() == "html":
            html = f"""<html><body><h1>{report.title}</h1><pre>{json.dumps(payload, indent=2)}</pre></body></html>"""
            target.write_text(html, encoding="utf-8")
            return

        msg = f"Unsupported export format: {output_format}"
        raise ValueError(msg)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix.upper()}-{self._counter:05d}"

    @staticmethod
    def _build_recommendations(summary: ErrorSummary) -> list[str]:
        recommendations: list[str] = []
        if summary.total_errors == 0:
            recommendations.append(
                "Maintain current validation configuration; no blocking issues detected.",
            )
        else:
            recommendations.append(
                "Review critical validation errors and schedule remediation work.",
            )
        return recommendations

    @staticmethod
    def _json_list(values: list[JSONObject]) -> list[JSONValue]:
        return [to_json_value(value) for value in values]

    @staticmethod
    def _extract_performance_metric(
        performance_report: JSONObject,
        metric_name: str,
    ) -> float | None:
        metrics_section = performance_report.get("metrics")
        if isinstance(metrics_section, dict):
            raw_value = metrics_section.get(metric_name)
            if isinstance(raw_value, int | float):
                return float(raw_value)
        return None

    @staticmethod
    def _average_quality_score(quality_metrics: JSONObject) -> float:
        score_block = quality_metrics.get("quality_score")
        if isinstance(score_block, dict):
            average_value = score_block.get("average")
            if isinstance(average_value, int | float):
                return float(average_value)
        return 0.0


__all__ = ["ValidationReport", "ValidationReportGenerator"]
