"""
src/quality_checks.py — Deterministic data-quality engine.

Checks:
    1. Row count — compare against the previous successful run.
    2. NULL percentage — per-column NULL rate against threshold.
    3. Duplicates — duplicate rows and duplicate customer IDs.
    4. Validity — numeric ranges and categorical value validation.
    5. Schema — consistency check.
    6. Freshness — ingestion timestamp tracking.

All checks are deterministic: the LLM is NEVER asked whether data is valid.
Returns structured results as a list of check-result dicts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from src.config import Config, get_config
from src.logging_config import get_logger
from src.schema_validator import validate_schema

logger = get_logger(__name__)

# Valid categories for key columns in the Telco dataset
VALID_CATEGORIES: dict[str, set[str]] = {
    "gender":          {"Male", "Female"},
    "partner":         {"Yes", "No"},
    "dependents":      {"Yes", "No"},
    "phone_service":   {"Yes", "No"},
    "churn":           {"Yes", "No"},
    "contract":        {"Month-to-month", "One year", "Two year"},
    "internet_service": {"DSL", "Fiber optic", "No"},
    "payment_method":  {
        "Electronic check", "Mailed check",
        "Bank transfer (automatic)", "Credit card (automatic)",
    },
    "paperless_billing": {"Yes", "No"},
}


def run_quality_checks(
    df: pd.DataFrame,
    previous_row_count: Optional[int] = None,
    config: Optional[Config] = None,
) -> list[dict[str, Any]]:
    """
    Execute all deterministic quality checks on the DataFrame.

    Args:
        df: The cleaned/transformed DataFrame.
        previous_row_count: Row count from the last successful run (for drift check).
        config: Application config.

    Returns a list of check-result dicts, each with:
        check, column (optional), status, severity, actual, expected/threshold, message
    """
    cfg = config or get_config()
    results: list[dict[str, Any]] = []

    results.extend(_check_row_count(df, previous_row_count, cfg))
    results.extend(_check_null_rates(df, cfg))
    results.extend(_check_duplicates(df, cfg))
    results.extend(_check_validity(df))
    results.extend(_check_schema(df))
    results.extend(_check_freshness())

    # Log summary
    fails = sum(1 for r in results if r["status"] == "FAIL")
    warns = sum(1 for r in results if r["status"] == "WARN")
    logger.info("Quality checks complete: %d total, %d FAIL, %d WARN", len(results), fails, warns)

    return results


# --- Individual check implementations ---


def _check_row_count(
    df: pd.DataFrame,
    previous_count: Optional[int],
    config: Config,
) -> list[dict[str, Any]]:
    """Compare current row count with the previous run."""
    current = len(df)

    if previous_count is None or previous_count == 0:
        return [
            {
                "check": "row_count",
                "column": None,
                "status": "PASS",
                "severity": "LOW",
                "actual": current,
                "threshold": None,
                "message": f"Row count: {current} (no previous run for comparison)",
            }
        ]

    pct_change = abs(current - previous_count) / previous_count * 100
    threshold = config.row_count_change_threshold

    if pct_change > threshold:
        return [
            {
                "check": "row_count",
                "column": None,
                "status": "FAIL",
                "severity": "HIGH",
                "actual": current,
                "threshold": f"±{threshold}% of {previous_count}",
                "message": (
                    f"Row count changed by {pct_change:.1f}% "
                    f"({previous_count} → {current}), threshold {threshold}%"
                ),
            }
        ]

    return [
        {
            "check": "row_count",
            "column": None,
            "status": "PASS",
            "severity": "LOW",
            "actual": current,
            "threshold": f"±{threshold}% of {previous_count}",
            "message": f"Row count within threshold ({pct_change:.1f}% change)",
        }
    ]


def _check_null_rates(df: pd.DataFrame, config: Config) -> list[dict[str, Any]]:
    """Calculate NULL rate for every column."""
    results: list[dict[str, Any]] = []
    threshold = config.null_rate_threshold
    total_rows = len(df)

    if total_rows == 0:
        return [
            {
                "check": "null_rate",
                "column": "ALL",
                "status": "FAIL",
                "severity": "CRITICAL",
                "actual": 100.0,
                "threshold": threshold,
                "message": "DataFrame is empty — 100% NULL rate",
            }
        ]

    for col in df.columns:
        null_count = int(df[col].isna().sum())
        null_pct = null_count / total_rows * 100

        if null_pct > threshold:
            results.append(
                {
                    "check": "null_rate",
                    "column": col,
                    "status": "FAIL",
                    "severity": "HIGH",
                    "actual": round(null_pct, 2),
                    "threshold": threshold,
                    "message": f"NULL rate {null_pct:.2f}% exceeds threshold {threshold}%",
                }
            )
        else:
            results.append(
                {
                    "check": "null_rate",
                    "column": col,
                    "status": "PASS",
                    "severity": "LOW",
                    "actual": round(null_pct, 2),
                    "threshold": threshold,
                    "message": f"NULL rate {null_pct:.2f}% within threshold",
                }
            )

    return results


def _check_duplicates(df: pd.DataFrame, config: Config) -> list[dict[str, Any]]:
    """Detect duplicate rows and duplicate customer IDs."""
    results: list[dict[str, Any]] = []
    threshold = config.duplicate_threshold
    total_rows = len(df)

    # Exact duplicate rows
    dup_rows = int(df.duplicated().sum())
    dup_pct = dup_rows / max(total_rows, 1) * 100

    if dup_pct > threshold:
        results.append(
            {
                "check": "duplicate_rows",
                "column": None,
                "status": "FAIL",
                "severity": "HIGH",
                "actual": dup_rows,
                "threshold": f"{threshold}% ({int(total_rows * threshold / 100)} rows)",
                "message": f"{dup_rows} duplicate rows ({dup_pct:.2f}%), exceeds {threshold}%",
            }
        )
    else:
        results.append(
            {
                "check": "duplicate_rows",
                "column": None,
                "status": "PASS",
                "severity": "LOW",
                "actual": dup_rows,
                "threshold": f"{threshold}%",
                "message": f"{dup_rows} duplicate rows ({dup_pct:.2f}%)",
            }
        )

    # Duplicate customer IDs
    id_col = "customer_id" if "customer_id" in df.columns else "customerid"
    if id_col in df.columns:
        dup_ids = int(df[id_col].duplicated().sum())
        if dup_ids > 0:
            results.append(
                {
                    "check": "duplicate_ids",
                    "column": id_col,
                    "status": "FAIL",
                    "severity": "HIGH",
                    "actual": dup_ids,
                    "threshold": 0,
                    "message": f"{dup_ids} duplicate customer IDs found",
                }
            )
        else:
            results.append(
                {
                    "check": "duplicate_ids",
                    "column": id_col,
                    "status": "PASS",
                    "severity": "LOW",
                    "actual": 0,
                    "threshold": 0,
                    "message": "No duplicate customer IDs",
                }
            )

    return results


def _check_validity(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Check numeric ranges and categorical value validity."""
    results: list[dict[str, Any]] = []

    # Numeric range checks
    numeric_checks = {
        "monthly_charges": (0, 500),
        "total_charges":   (0, 50000),
        "tenure":          (0, 200),
        "senior_citizen":  (0, 1),
    }

    for col, (low, high) in numeric_checks.items():
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce")
        out_of_range = int(((series < low) | (series > high)).sum())

        if out_of_range > 0:
            results.append(
                {
                    "check": "numeric_range",
                    "column": col,
                    "status": "FAIL",
                    "severity": "MEDIUM",
                    "actual": out_of_range,
                    "threshold": f"[{low}, {high}]",
                    "message": f"{out_of_range} values outside range [{low}, {high}]",
                }
            )
        else:
            results.append(
                {
                    "check": "numeric_range",
                    "column": col,
                    "status": "PASS",
                    "severity": "LOW",
                    "actual": 0,
                    "threshold": f"[{low}, {high}]",
                    "message": f"All values within [{low}, {high}]",
                }
            )

    # Categorical checks
    for col, valid_vals in VALID_CATEGORIES.items():
        if col not in df.columns:
            continue
        actual_vals = set(df[col].dropna().unique())
        unexpected = actual_vals - valid_vals

        if unexpected:
            results.append(
                {
                    "check": "categorical_validity",
                    "column": col,
                    "status": "FAIL",
                    "severity": "MEDIUM",
                    "actual": sorted(unexpected),
                    "threshold": sorted(valid_vals),
                    "message": f"Unexpected values in {col}: {sorted(unexpected)}",
                }
            )
        else:
            results.append(
                {
                    "check": "categorical_validity",
                    "column": col,
                    "status": "PASS",
                    "severity": "LOW",
                    "actual": sorted(actual_vals),
                    "threshold": sorted(valid_vals),
                    "message": f"All values valid in {col}",
                }
            )

    return results


def _check_schema(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Run schema validation and convert to quality-check format."""
    schema_result = validate_schema(df)
    status = schema_result["status"]
    severity = "CRITICAL" if status == "FAIL" else ("MEDIUM" if status == "WARN" else "LOW")

    return [
        {
            "check": "schema",
            "column": None,
            "status": status,
            "severity": severity,
            "actual": schema_result,
            "threshold": "Expected schema",
            "message": schema_result["message"],
        }
    ]


def _check_freshness() -> list[dict[str, Any]]:
    """Record ingestion timestamp for freshness tracking."""
    now = datetime.now(timezone.utc)
    return [
        {
            "check": "freshness",
            "column": None,
            "status": "PASS",
            "severity": "LOW",
            "actual": now.isoformat(),
            "threshold": "Current time",
            "message": f"Data ingested at {now.isoformat()}",
        }
    ]
