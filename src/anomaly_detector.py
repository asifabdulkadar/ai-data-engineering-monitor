"""
src/anomaly_detector.py — Anomaly detection engine.

Detects:
    * Row-count drops and spikes.
    * NULL-rate spikes.
    * Duplicate spikes.
    * Schema changes.
    * Unexpected categories.
    * Suspicious numeric changes.

Uses configurable thresholds from environment variables.
All detection is deterministic — no LLM involvement.
"""

from __future__ import annotations

from typing import Any, Optional

from src.config import Config, get_config
from src.logging_config import get_logger

logger = get_logger(__name__)


def detect_anomalies(
    quality_results: list[dict[str, Any]],
    etl_result: dict[str, Any],
    previous_row_count: Optional[int] = None,
    config: Optional[Config] = None,
) -> list[dict[str, Any]]:
    """
    Analyse quality-check results and ETL metrics to flag anomalies.

    Returns a list of anomaly dicts:
        {
            "anomaly_type": str,
            "severity": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
            "description": str,
            "details": dict,
        }
    """
    cfg = config or get_config()
    anomalies: list[dict[str, Any]] = []

    anomalies.extend(_detect_row_count_anomalies(etl_result, previous_row_count, cfg))
    anomalies.extend(_detect_null_anomalies(quality_results, cfg))
    anomalies.extend(_detect_duplicate_anomalies(quality_results, cfg))
    anomalies.extend(_detect_schema_anomalies(quality_results))
    anomalies.extend(_detect_category_anomalies(quality_results))
    anomalies.extend(_detect_numeric_anomalies(quality_results))
    anomalies.extend(_detect_pipeline_failure(etl_result))

    logger.info("Anomaly detection complete: %d anomalies found", len(anomalies))
    for a in anomalies:
        logger.warning("ANOMALY [%s] %s: %s", a["severity"], a["anomaly_type"], a["description"])

    return anomalies


# --- Individual detectors ---


def _detect_row_count_anomalies(
    etl_result: dict[str, Any],
    previous_count: Optional[int],
    config: Config,
) -> list[dict[str, Any]]:
    """Detect row-count drops and spikes."""
    anomalies: list[dict[str, Any]] = []
    current = etl_result.get("rows_processed", 0)

    if previous_count is None or previous_count == 0:
        return anomalies

    pct_change = (current - previous_count) / previous_count * 100
    threshold = config.row_count_change_threshold

    if pct_change < -threshold:
        anomalies.append({
            "anomaly_type": "row_count_drop",
            "severity": "HIGH",
            "description": (
                f"Row count dropped by {abs(pct_change):.1f}% "
                f"({previous_count} → {current})"
            ),
            "details": {
                "previous": previous_count,
                "current": current,
                "change_pct": round(pct_change, 2),
                "threshold_pct": threshold,
            },
        })

    if pct_change > threshold:
        anomalies.append({
            "anomaly_type": "row_count_spike",
            "severity": "MEDIUM",
            "description": (
                f"Row count increased by {pct_change:.1f}% "
                f"({previous_count} → {current})"
            ),
            "details": {
                "previous": previous_count,
                "current": current,
                "change_pct": round(pct_change, 2),
                "threshold_pct": threshold,
            },
        })

    return anomalies


def _detect_null_anomalies(
    quality_results: list[dict[str, Any]],
    config: Config,
) -> list[dict[str, Any]]:
    """Detect NULL-rate spikes (any column exceeding the threshold)."""
    anomalies: list[dict[str, Any]] = []

    for check in quality_results:
        if check["check"] == "null_rate" and check["status"] == "FAIL":
            anomalies.append({
                "anomaly_type": "null_rate_spike",
                "severity": "HIGH",
                "description": (
                    f"Column '{check['column']}' NULL rate is {check['actual']}%, "
                    f"exceeds threshold {config.null_rate_threshold}%"
                ),
                "details": {
                    "column": check["column"],
                    "null_pct": check["actual"],
                    "threshold": config.null_rate_threshold,
                },
            })

    return anomalies


def _detect_duplicate_anomalies(
    quality_results: list[dict[str, Any]],
    config: Config,
) -> list[dict[str, Any]]:
    """Detect duplicate spikes."""
    anomalies: list[dict[str, Any]] = []

    for check in quality_results:
        if check["check"] in ("duplicate_rows", "duplicate_ids") and check["status"] == "FAIL":
            anomalies.append({
                "anomaly_type": "duplicate_spike",
                "severity": "HIGH",
                "description": f"{check['check']}: {check['message']}",
                "details": {
                    "check": check["check"],
                    "actual": check["actual"],
                },
            })

    return anomalies


def _detect_schema_anomalies(quality_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect schema changes."""
    anomalies: list[dict[str, Any]] = []

    for check in quality_results:
        if check["check"] == "schema" and check["status"] in ("FAIL", "WARN"):
            anomalies.append({
                "anomaly_type": "schema_change",
                "severity": "CRITICAL" if check["status"] == "FAIL" else "MEDIUM",
                "description": check["message"],
                "details": check.get("actual", {}),
            })

    return anomalies


def _detect_category_anomalies(quality_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect unexpected category values."""
    anomalies: list[dict[str, Any]] = []

    for check in quality_results:
        if check["check"] == "categorical_validity" and check["status"] == "FAIL":
            anomalies.append({
                "anomaly_type": "unexpected_category",
                "severity": "MEDIUM",
                "description": check["message"],
                "details": {
                    "column": check["column"],
                    "unexpected_values": check["actual"],
                },
            })

    return anomalies


def _detect_numeric_anomalies(quality_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect suspicious numeric range violations."""
    anomalies: list[dict[str, Any]] = []

    for check in quality_results:
        if check["check"] == "numeric_range" and check["status"] == "FAIL":
            anomalies.append({
                "anomaly_type": "numeric_range_violation",
                "severity": "MEDIUM",
                "description": check["message"],
                "details": {
                    "column": check["column"],
                    "out_of_range_count": check["actual"],
                    "expected_range": check["threshold"],
                },
            })

    return anomalies


def _detect_pipeline_failure(etl_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect if the pipeline itself failed."""
    if etl_result.get("status") == "FAILED":
        return [{
            "anomaly_type": "pipeline_failure",
            "severity": "CRITICAL",
            "description": f"Pipeline failed: {etl_result.get('error_message', 'Unknown error')}",
            "details": {
                "error": etl_result.get("error_message"),
                "run_id": etl_result.get("run_id"),
            },
        }]
    return []
