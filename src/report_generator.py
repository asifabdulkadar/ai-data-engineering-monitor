"""
src/report_generator.py — AI incident report persistence and formatting.

Provides:
    save_incident_report()  — Persist an incident report to the database.
    format_report_text()    — Pretty-print a report for console/log output.
    get_latest_report()     — Fetch the most recent report from the DB.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import text

from src.config import Config, get_config
from src.database import get_connection
from src.logging_config import get_logger

logger = get_logger(__name__)


def save_incident_report(
    run_id: str,
    report: dict[str, Any],
    config: Optional[Config] = None,
) -> None:
    """Persist an AI incident report to the incident_reports table."""
    cfg = config or get_config()

    sql = """
        INSERT INTO incident_reports
            (run_id, incident_title, severity, summary,
             confirmed_facts, possible_root_causes,
             business_impact, recommended_actions, confidence)
        VALUES
            (:run_id, :incident_title, :severity, :summary,
             :confirmed_facts, :possible_root_causes,
             :business_impact, :recommended_actions, :confidence)
    """

    params = {
        "run_id":               run_id,
        "incident_title":       report.get("incident_title", ""),
        "severity":             report.get("severity", "LOW"),
        "summary":              report.get("summary", ""),
        "confirmed_facts":      json.dumps(report.get("confirmed_facts", [])),
        "possible_root_causes": json.dumps(report.get("possible_root_causes", [])),
        "business_impact":      report.get("business_impact", ""),
        "recommended_actions":  json.dumps(report.get("recommended_actions", [])),
        "confidence":           report.get("confidence", 0.0),
    }

    try:
        with get_connection(cfg) as conn:
            conn.execute(text(sql), params)
        logger.info("Incident report saved for run %s", run_id)
    except Exception as exc:
        logger.error("Failed to save incident report: %s", exc)


def get_latest_report(config: Optional[Config] = None) -> Optional[dict[str, Any]]:
    """Fetch the most recent incident report from the database."""
    cfg = config or get_config()
    sql = """
        SELECT run_id, incident_title, severity, summary,
               confirmed_facts, possible_root_causes,
               business_impact, recommended_actions, confidence,
               created_at
        FROM incident_reports
        ORDER BY created_at DESC
        LIMIT 1
    """
    try:
        with get_connection(cfg) as conn:
            result = conn.execute(text(sql))
            row = result.fetchone()
            if row is None:
                return None
            data = dict(row._mapping)
            # Parse JSON fields
            for field in ("confirmed_facts", "possible_root_causes", "recommended_actions"):
                if isinstance(data.get(field), str):
                    try:
                        data[field] = json.loads(data[field])
                    except json.JSONDecodeError:
                        data[field] = [data[field]]
            return data
    except Exception as exc:
        logger.error("Failed to fetch latest report: %s", exc)
        return None


def format_report_text(report: dict[str, Any]) -> str:
    """Format an incident report as human-readable text for console output."""
    lines: list[str] = []
    lines.append("")
    lines.append("AI INCIDENT REPORT")
    lines.append("-" * 40)
    lines.append(f"Title:      {report.get('incident_title', 'N/A')}")
    lines.append(f"Severity:   {report.get('severity', 'N/A')}")
    lines.append(f"Summary:    {report.get('summary', 'N/A')}")
    lines.append(f"Confidence: {report.get('confidence', 'N/A')}")

    facts = report.get("confirmed_facts", [])
    if facts:
        lines.append("")
        lines.append("Confirmed Facts:")
        for fact in facts:
            lines.append(f"  • {fact}")

    causes = report.get("possible_root_causes", [])
    if causes:
        lines.append("")
        lines.append("Possible Root Causes:")
        for cause in causes:
            lines.append(f"  • {cause}")

    impact = report.get("business_impact")
    if impact:
        lines.append("")
        lines.append(f"Business Impact: {impact}")

    actions = report.get("recommended_actions", [])
    if actions:
        lines.append("")
        lines.append("Recommended Actions:")
        for action in actions:
            lines.append(f"  • {action}")

    ai_status = "Available" if report.get("ai_available", False) else "Unavailable (fallback used)"
    lines.append("")
    lines.append(f"AI Status:  {ai_status}")
    lines.append("-" * 40)

    return "\n".join(lines)
