"""
src/agent.py — AI monitoring agent powered by OpenAI.

The agent receives STRUCTURED, DETERMINISTIC monitoring results
(quality checks + anomalies) and uses the LLM to INTERPRET them.

Flow:
    Python/SQL → Facts → LLM → Interpretation

The LLM does NOT independently determine raw numerical failures.
It distinguishes confirmed facts from hypotheses.
If no anomalies exist, it returns a healthy status.

If OpenAI is unavailable, the function returns a fallback result
so the rest of the application continues working.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from src.config import Config, get_config
from src.logging_config import get_logger

logger = get_logger(__name__)

# Output schema the LLM must follow
INCIDENT_SCHEMA = {
    "incident_title": "",
    "severity": "LOW|MEDIUM|HIGH|CRITICAL",
    "summary": "",
    "confirmed_facts": [],
    "possible_root_causes": [],
    "business_impact": "",
    "recommended_actions": [],
    "confidence": 0.0,
}


def analyse_with_ai(
    etl_result: dict[str, Any],
    quality_results: list[dict[str, Any]],
    anomalies: list[dict[str, Any]],
    config: Optional[Config] = None,
) -> dict[str, Any]:
    """
    Send monitoring data to OpenAI for interpretation.

    Returns a structured incident report dict. Falls back gracefully
    if OpenAI is unavailable.
    """
    cfg = config or get_config()

    # No anomalies → healthy status, no need to call the LLM
    if not anomalies:
        logger.info("No anomalies detected — returning healthy status")
        return {
            "incident_title": "Pipeline Healthy",
            "severity": "NONE",
            "summary": "All quality checks passed. No anomalies detected.",
            "confirmed_facts": ["All quality checks passed", "No anomalies detected"],
            "possible_root_causes": [],
            "business_impact": "None — pipeline operating normally",
            "recommended_actions": [],
            "confidence": 1.0,
            "ai_available": True,
        }

    # Check if OpenAI is configured
    if not cfg.has_openai():
        logger.warning("OpenAI not configured — returning deterministic fallback")
        return _fallback_report(anomalies)

    # Call OpenAI
    try:
        return _call_openai(etl_result, quality_results, anomalies, cfg)
    except Exception as exc:
        logger.error("OpenAI call failed: %s — using fallback report", exc)
        return _fallback_report(anomalies)


def _call_openai(
    etl_result: dict[str, Any],
    quality_results: list[dict[str, Any]],
    anomalies: list[dict[str, Any]],
    config: Config,
) -> dict[str, Any]:
    """Make the actual OpenAI API call."""
    from openai import OpenAI  # import here to avoid hard dependency

    client = OpenAI(api_key=config.openai_api_key)

    # Build the facts section — only confirmed, deterministic data
    failed_checks = [q for q in quality_results if q["status"] == "FAIL"]
    facts = {
        "pipeline_status": etl_result.get("status"),
        "rows_received": etl_result.get("rows_received"),
        "rows_processed": etl_result.get("rows_processed"),
        "rows_rejected": etl_result.get("rows_rejected"),
        "error_message": etl_result.get("error_message"),
        "failed_quality_checks": _serialize_checks(failed_checks),
        "anomalies": _serialize_anomalies(anomalies),
    }

    system_prompt = """You are a senior Data Engineering monitoring agent.
You receive DETERMINISTIC monitoring results from a data pipeline (quality checks
and anomaly detections produced by Python code — NOT by AI).

Your job:
1. INTERPRET the results — explain what happened and why it matters.
2. CLEARLY SEPARATE confirmed facts (provided to you) from your hypotheses.
3. Suggest root causes, business impact, and remediation steps.
4. Be concise and actionable.

You MUST respond with ONLY valid JSON matching this schema:
{
    "incident_title": "string",
    "severity": "LOW|MEDIUM|HIGH|CRITICAL",
    "summary": "string",
    "confirmed_facts": ["string", ...],
    "possible_root_causes": ["string", ...],
    "business_impact": "string",
    "recommended_actions": ["string", ...],
    "confidence": 0.0-1.0
}

IMPORTANT:
- "confirmed_facts" must be facts from the monitoring data, not your guesses.
- "possible_root_causes" are your hypotheses — label them as such.
- "confidence" reflects how confident you are in your interpretation (0.0-1.0).
- Do NOT include markdown, code fences, or any text outside the JSON object.
"""

    user_prompt = f"""Analyse the following data pipeline monitoring results and generate an incident report.

DETERMINISTIC FACTS (produced by Python code):
{json.dumps(facts, indent=2, default=str)}

Generate the incident report JSON."""

    logger.info("Calling OpenAI model: %s", config.openai_model)
    response = client.chat.completions.create(
        model=config.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,        # Low temperature for consistent analysis
        max_tokens=1000,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content or "{}"
    report = json.loads(content)
    report["ai_available"] = True
    logger.info("AI incident report generated: %s", report.get("incident_title"))
    return report


def _fallback_report(anomalies: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a deterministic fallback when OpenAI is unavailable."""
    max_severity = _max_severity(anomalies)
    descriptions = [a["description"] for a in anomalies]

    return {
        "incident_title": f"Pipeline Anomaly Detected ({len(anomalies)} issue(s))",
        "severity": max_severity,
        "summary": f"{len(anomalies)} anomaly(ies) detected. AI analysis unavailable.",
        "confirmed_facts": descriptions,
        "possible_root_causes": ["AI analysis unavailable — manual investigation required"],
        "business_impact": "Unknown — requires manual assessment",
        "recommended_actions": [
            "Review the anomaly details above",
            "Check pipeline logs for errors",
            "Verify source data integrity",
            "Re-run pipeline after fixing issues",
        ],
        "confidence": 0.0,
        "ai_available": False,
    }


def _max_severity(anomalies: list[dict[str, Any]]) -> str:
    """Return the highest severity among anomalies."""
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    max_sev = "LOW"
    for a in anomalies:
        sev = a.get("severity", "LOW")
        if order.get(sev, 0) > order.get(max_sev, 0):
            max_sev = sev
    return max_sev


def _serialize_checks(checks: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Serialize quality checks for the LLM prompt (string-safe)."""
    return [
        {
            "check": str(c.get("check")),
            "column": str(c.get("column", "")),
            "actual": str(c.get("actual")),
            "threshold": str(c.get("threshold", "")),
            "message": str(c.get("message")),
        }
        for c in checks
    ]


def _serialize_anomalies(anomalies: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Serialize anomalies for the LLM prompt (string-safe)."""
    return [
        {
            "type": str(a.get("anomaly_type")),
            "severity": str(a.get("severity")),
            "description": str(a.get("description")),
        }
        for a in anomalies
    ]
