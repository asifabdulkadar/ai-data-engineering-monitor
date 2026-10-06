"""
src/monitoring.py — Monitoring orchestrator.

Orchestrates the full monitoring flow:
    Pipeline (ETL) → Quality Checks → Anomaly Detection
    → Database persistence → AI analysis → Incident Report

Produces a clean MonitoringResult object that the dashboard and CLI consume.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from src.agent import analyse_with_ai
from src.anomaly_detector import detect_anomalies
from src.config import Config, get_config
from src.database import get_connection
from src.etl import run_etl
from src.logging_config import get_logger
from src.quality_checks import run_quality_checks
from src.report_generator import format_report_text, save_incident_report

logger = get_logger(__name__)


@dataclass
class MonitoringResult:
    """Container for the full monitoring output."""

    run_id: str = ""
    pipeline_name: str = ""
    status: str = "UNKNOWN"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    rows_received: int = 0
    rows_processed: int = 0
    rows_rejected: int = 0
    error_message: Optional[str] = None
    quality_results: list[dict[str, Any]] = field(default_factory=list)
    anomalies: list[dict[str, Any]] = field(default_factory=list)
    incident_report: dict[str, Any] = field(default_factory=dict)
    overall_status: str = "UNKNOWN"  # HEALTHY / DEGRADED / FAILED

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON/display."""
        return {
            "run_id": self.run_id,
            "pipeline_name": self.pipeline_name,
            "status": self.status,
            "start_time": str(self.start_time) if self.start_time else None,
            "end_time": str(self.end_time) if self.end_time else None,
            "rows_received": self.rows_received,
            "rows_processed": self.rows_processed,
            "rows_rejected": self.rows_rejected,
            "error_message": self.error_message,
            "quality_summary": _quality_summary(self.quality_results),
            "anomaly_count": len(self.anomalies),
            "overall_status": self.overall_status,
        }


def _quality_summary(results: list[dict[str, Any]]) -> dict[str, str]:
    """Summarise quality results by check type."""
    summary: dict[str, str] = {}
    for r in results:
        check = r.get("check", "unknown")
        status = r.get("status", "UNKNOWN")
        # A check type fails if ANY of its instances fail
        if check not in summary or status == "FAIL":
            summary[check] = status
    return summary


def run_monitoring(
    file_path: Optional[str] = None,
    config: Optional[Config] = None,
    skip_storage: bool = False,
    skip_db: bool = False,
) -> MonitoringResult:
    """
    Execute the full monitoring pipeline.

    Steps:
        1. Run ETL pipeline.
        2. Get previous run's row count (if DB available).
        3. Run quality checks.
        4. Detect anomalies.
        5. Persist quality results and anomalies.
        6. If anomalies exist, call the AI agent.
        7. Persist incident report.
        8. Return MonitoringResult.
    """
    cfg = config or get_config()
    result = MonitoringResult()

    # 1. Run ETL
    etl_result = run_etl(file_path=file_path, config=cfg, skip_storage=skip_storage, skip_db=skip_db)
    result.run_id = etl_result["run_id"]
    result.pipeline_name = etl_result["pipeline_name"]
    result.status = etl_result["status"]
    result.start_time = etl_result["start_time"]
    result.end_time = etl_result["end_time"]
    result.rows_received = etl_result["rows_received"]
    result.rows_processed = etl_result["rows_processed"]
    result.rows_rejected = etl_result["rows_rejected"]
    result.error_message = etl_result.get("error_message")

    df = etl_result.get("dataframe")

    # 2. Get previous row count
    previous_row_count = None
    if not skip_db:
        previous_row_count = _get_previous_row_count(cfg, result.run_id)

    # 3. Quality checks (run even if ETL failed, on whatever data is available)
    if df is not None and not df.empty:
        result.quality_results = run_quality_checks(
            df, previous_row_count=previous_row_count, config=cfg
        )
    else:
        result.quality_results = [
            {
                "check": "data_availability",
                "column": None,
                "status": "FAIL",
                "severity": "CRITICAL",
                "actual": 0,
                "threshold": "> 0 rows",
                "message": "No data available for quality checks",
            }
        ]

    # 4. Anomaly detection
    result.anomalies = detect_anomalies(
        result.quality_results, etl_result,
        previous_row_count=previous_row_count, config=cfg,
    )

    # 5. Persist quality results and anomalies
    if not skip_db:
        _persist_quality_results(result.run_id, result.quality_results, cfg)
        _persist_anomalies(result.run_id, result.anomalies, cfg)

    # 6. AI analysis
    result.incident_report = analyse_with_ai(
        etl_result, result.quality_results, result.anomalies, cfg
    )

    # 7. Persist incident report
    if not skip_db and result.incident_report:
        save_incident_report(result.run_id, result.incident_report, cfg)

    # 8. Overall status
    if result.status == "FAILED" or any(
        a["severity"] in ("HIGH", "CRITICAL") for a in result.anomalies
    ):
        result.overall_status = "FAILED"
    elif result.anomalies:
        result.overall_status = "DEGRADED"
    else:
        result.overall_status = "HEALTHY"

    return result


def _get_previous_row_count(config: Config, current_run_id: str) -> Optional[int]:
    """Get rows_processed from the last successful pipeline run (before current)."""
    sql = """
        SELECT rows_processed FROM pipeline_runs
        WHERE status = 'SUCCESS' AND run_id != :current_run_id
        ORDER BY start_time DESC LIMIT 1
    """
    try:
        with get_connection(config) as conn:
            row = conn.execute(text(sql), {"current_run_id": current_run_id}).fetchone()
            if row:
                return row[0]
    except Exception as exc:
        logger.warning("Could not fetch previous row count: %s", exc)
    return None


def _persist_quality_results(
    run_id: str,
    results: list[dict[str, Any]],
    config: Config,
) -> None:
    """Insert quality-check results into data_quality_results."""
    sql = """
        INSERT INTO data_quality_results
            (run_id, check_name, status, severity, actual_value, expected_value, message)
        VALUES
            (:run_id, :check_name, :status, :severity, :actual_value, :expected_value, :message)
    """
    try:
        with get_connection(config) as conn:
            for r in results:
                conn.execute(text(sql), {
                    "run_id":         run_id,
                    "check_name":     r.get("check", ""),
                    "status":         r.get("status", "UNKNOWN"),
                    "severity":       r.get("severity", "LOW"),
                    "actual_value":   str(r.get("actual", "")),
                    "expected_value": str(r.get("threshold", "")),
                    "message":        r.get("message", ""),
                })
        logger.info("Persisted %d quality results for run %s", len(results), run_id)
    except Exception as exc:
        logger.error("Failed to persist quality results: %s", exc)


def _persist_anomalies(
    run_id: str,
    anomalies: list[dict[str, Any]],
    config: Config,
) -> None:
    """Insert anomaly events into anomaly_events."""
    sql = """
        INSERT INTO anomaly_events
            (run_id, anomaly_type, severity, description)
        VALUES
            (:run_id, :anomaly_type, :severity, :description)
    """
    try:
        with get_connection(config) as conn:
            for a in anomalies:
                conn.execute(text(sql), {
                    "run_id":       run_id,
                    "anomaly_type": a.get("anomaly_type", ""),
                    "severity":     a.get("severity", "LOW"),
                    "description":  a.get("description", ""),
                })
        logger.info("Persisted %d anomalies for run %s", len(anomalies), run_id)
    except Exception as exc:
        logger.error("Failed to persist anomalies: %s", exc)


def print_summary(result: MonitoringResult) -> None:
    """Print a human-readable pipeline summary to stdout."""
    qsum = _quality_summary(result.quality_results)

    print("\n" + "=" * 50)
    if result.overall_status == "HEALTHY":
        print("AI DATA ENGINEERING MONITOR")
    else:
        print("PIPELINE ANOMALY DETECTED")
    print("=" * 50)
    print(f"Pipeline:          {result.pipeline_name}")
    print(f"Run ID:            {result.run_id}")
    print(f"Rows received:     {result.rows_received}")
    print(f"Rows processed:    {result.rows_processed}")
    print(f"Rows rejected:     {result.rows_rejected}")
    print(f"Schema:            {qsum.get('schema', 'N/A')}")
    print(f"Null checks:       {qsum.get('null_rate', 'N/A')}")
    print(f"Duplicate checks:  {qsum.get('duplicate_rows', 'N/A')}")
    print(f"Volume check:      {qsum.get('row_count', 'N/A')}")
    print(f"Freshness:         {qsum.get('freshness', 'N/A')}")
    print(f"Overall status:    {result.overall_status}")

    if result.incident_report:
        print(format_report_text(result.incident_report))

    print("=" * 50)
