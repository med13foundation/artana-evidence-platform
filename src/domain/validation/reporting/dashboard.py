"""Simplified validation dashboard used by the integration tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from src.type_definitions.common import JSONObject

from .error_reporting import ErrorReporter, ErrorSummary
from .metrics import MetricsCollector


@dataclass
class DashboardConfig:
    refresh_interval_seconds: int = 120
    display_metrics: list[str] | None = None


@dataclass
class DashboardData:
    timestamp: datetime
    system_health: float
    quality_metrics: JSONObject
    error_summary: ErrorSummary
    performance_metrics: JSONObject
    alerts: list[JSONObject]


class ValidationDashboard:
    """Provide a small typed API for the tests to interact with."""

    def __init__(
        self,
        error_reporter: ErrorReporter,
        metrics_collector: MetricsCollector,
        config: DashboardConfig | None = None,
    ) -> None:
        self._error_reporter = error_reporter
        self._metrics = metrics_collector
        self._config = config or DashboardConfig()
        self._cached: DashboardData | None = None
        self._last_refresh: datetime | None = None

    def get_dashboard_data(self, force_refresh: bool = False) -> DashboardData:
        now = datetime.now(UTC)
        needs_refresh = (
            force_refresh
            or self._cached is None
            or self._last_refresh is None
            or (now - self._last_refresh).total_seconds()
            > self._config.refresh_interval_seconds
        )

        if needs_refresh:
            self._cached = self._collect_data(timestamp=now)
            self._last_refresh = now

        return self._cached  # type: ignore[return-value]

    def generate_report(self, output_format: str = "json") -> str:
        data = self.get_dashboard_data(force_refresh=True)
        payload = {
            "generated_at": data.timestamp.isoformat(),
            "system_health": data.system_health,
            "quality_metrics": data.quality_metrics,
            "performance_metrics": data.performance_metrics,
            "total_errors": data.error_summary.total_errors,
            "alerts": [
                {
                    **alert,
                    "timestamp": (
                        timestamp.isoformat()
                        if isinstance(timestamp, datetime)
                        else timestamp
                    ),
                }
                for alert in data.alerts
                for timestamp in [alert.get("timestamp")]
            ],
        }

        if output_format.lower() == "json":
            return json.dumps(payload, indent=2)
        if output_format.lower() == "html":
            return f"""<html><body><h1>Validation Dashboard</h1><pre>{json.dumps(payload, indent=2)}</pre></body></html>"""
        msg = f"Unsupported report format: {output_format}"
        raise ValueError(msg)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _collect_data(self, timestamp: datetime) -> DashboardData:
        quality_summary = self._metrics.get_metric_summary("validation.quality_score")
        error_summary = self._error_reporter.get_error_summary()
        throughput_summary = self._metrics.get_metric_summary("pipeline.throughput")
        execution_summary = self._metrics.get_metric_summary("pipeline.execution_time")

        quality_metrics: JSONObject = {}
        if quality_summary:
            quality_metrics["quality_score"] = {
                "average": quality_summary.average,
                "min": quality_summary.minimum,
                "max": quality_summary.maximum,
            }

        performance_metrics: JSONObject = {}
        if throughput_summary:
            performance_metrics["throughput_items_per_second"] = (
                throughput_summary.average
            )
        if execution_summary:
            performance_metrics["execution_time_seconds"] = execution_summary.average

        alerts = self._metrics.get_alerts()

        return DashboardData(
            timestamp=timestamp,
            system_health=self._metrics.get_system_health_score(),
            quality_metrics=quality_metrics,
            error_summary=error_summary,
            performance_metrics=performance_metrics,
            alerts=alerts,
        )


__all__ = ["DashboardConfig", "DashboardData", "ValidationDashboard"]
