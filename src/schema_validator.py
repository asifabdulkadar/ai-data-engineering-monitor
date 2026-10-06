"""
src/schema_validator.py — Schema validation for the ingested DataFrame.

Checks:
    * Required columns are present.
    * No unexpected columns exist.
    * Data types are correct after normalisation.

Returns a structured validation result dict.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.logging_config import get_logger

logger = get_logger(__name__)

# Expected schema: column_name → expected pandas dtype category
EXPECTED_SCHEMA: dict[str, str] = {
    "customer_id":       "object",
    "gender":            "object",
    "senior_citizen":    "int",        # 0 or 1
    "partner":           "object",
    "dependents":        "object",
    "tenure":            "int",
    "phone_service":     "object",
    "multiple_lines":    "object",
    "internet_service":  "object",
    "online_security":   "object",
    "online_backup":     "object",
    "device_protection": "object",
    "tech_support":      "object",
    "streaming_tv":      "object",
    "streaming_movies":  "object",
    "contract":          "object",
    "paperless_billing": "object",
    "payment_method":    "object",
    "monthly_charges":   "float",
    "total_charges":     "float",
    "churn":             "object",
}


def _dtype_matches(actual_dtype: str, expected_category: str) -> bool:
    """Check if the actual pandas dtype matches the expected category."""
    actual = str(actual_dtype).lower()
    if expected_category == "object":
        return "object" in actual or "string" in actual
    if expected_category == "int":
        return "int" in actual
    if expected_category == "float":
        return "float" in actual or "int" in actual  # int is promotable to float
    return False


def validate_schema(df: pd.DataFrame) -> dict[str, Any]:
    """
    Validate the DataFrame schema against the expected Telco dataset schema.

    Returns:
        {
            "status": "PASS" | "FAIL",
            "missing_columns": [...],
            "unexpected_columns": [...],
            "type_mismatches": [...],
            "message": "..."
        }
    """
    expected_cols = set(EXPECTED_SCHEMA.keys())
    actual_cols = set(df.columns)

    missing_columns = sorted(expected_cols - actual_cols)
    unexpected_columns = sorted(actual_cols - expected_cols)

    # Type check only for columns that are present and expected
    type_mismatches: list[dict[str, str]] = []
    for col, expected_type in EXPECTED_SCHEMA.items():
        if col in actual_cols:
            actual_dtype = str(df[col].dtype)
            if not _dtype_matches(actual_dtype, expected_type):
                type_mismatches.append(
                    {
                        "column": col,
                        "expected": expected_type,
                        "actual": actual_dtype,
                    }
                )

    # Determine overall status
    if missing_columns:
        status = "FAIL"
        message = f"Required column(s) missing: {missing_columns}"
    elif type_mismatches:
        status = "FAIL"
        message = f"Type mismatches found: {[m['column'] for m in type_mismatches]}"
    elif unexpected_columns:
        status = "WARN"
        message = f"Unexpected column(s): {unexpected_columns}"
    else:
        status = "PASS"
        message = "Schema validation passed"

    result = {
        "status": status,
        "missing_columns": missing_columns,
        "unexpected_columns": unexpected_columns,
        "type_mismatches": type_mismatches,
        "message": message,
    }

    logger.info("Schema validation: %s — %s", status, message)
    return result
