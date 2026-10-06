"""
tests/test_quality_checks.py — Unit tests for the data quality engine.

Tests:
    - NULL detection across columns.
    - Duplicate detection (rows and IDs).
    - Row-count anomaly (drift from previous run).
    - Threshold logic.
    - Categorical validity checks.
    - Numeric range checks.

All tests use synthetic DataFrames — no database or API required.
"""

import pandas as pd
import pytest

from src.config import Config
from src.quality_checks import run_quality_checks


def _make_config(**overrides) -> Config:
    """Create a Config with sensible test defaults."""
    defaults = {
        "row_count_change_threshold": 20.0,
        "null_rate_threshold": 10.0,
        "duplicate_threshold": 5.0,
    }
    defaults.update(overrides)
    # We can't easily override frozen dataclass fields, so we set env vars
    import os
    for k, v in defaults.items():
        env_key = k.upper()
        os.environ[env_key] = str(v)
    return Config()


def _make_clean_df(n: int = 100) -> pd.DataFrame:
    """Create a clean synthetic DataFrame matching the Telco schema (post-ETL rename)."""
    return pd.DataFrame({
        "customer_id":       [f"CUST-{i:04d}" for i in range(n)],
        "gender":            ["Male" if i % 2 == 0 else "Female" for i in range(n)],
        "senior_citizen":    [0] * n,
        "partner":           ["Yes" if i % 3 == 0 else "No" for i in range(n)],
        "dependents":        ["No"] * n,
        "tenure":            list(range(n)),
        "phone_service":     ["Yes"] * n,
        "multiple_lines":    ["No"] * n,
        "internet_service":  ["DSL"] * n,
        "online_security":   ["No"] * n,
        "online_backup":     ["No"] * n,
        "device_protection": ["No"] * n,
        "tech_support":      ["No"] * n,
        "streaming_tv":      ["No"] * n,
        "streaming_movies":  ["No"] * n,
        "contract":          ["Month-to-month"] * n,
        "paperless_billing": ["Yes"] * n,
        "payment_method":    ["Electronic check"] * n,
        "monthly_charges":   [50.0 + i * 0.5 for i in range(n)],
        "total_charges":     [100.0 + i * 10.0 for i in range(n)],
        "churn":             ["No" if i % 5 != 0 else "Yes" for i in range(n)],
    })


class TestNullDetection:
    """Tests for NULL rate detection."""

    def test_no_nulls_passes(self):
        df = _make_clean_df(100)
        config = _make_config(null_rate_threshold=10.0)
        results = run_quality_checks(df, config=config)
        null_checks = [r for r in results if r["check"] == "null_rate"]
        assert all(r["status"] == "PASS" for r in null_checks)

    def test_high_null_rate_fails(self):
        df = _make_clean_df(100)
        # Inject 50% NULLs into monthly_charges
        df.loc[:49, "monthly_charges"] = None
        config = _make_config(null_rate_threshold=10.0)
        results = run_quality_checks(df, config=config)
        null_fails = [r for r in results if r["check"] == "null_rate" and r["status"] == "FAIL"]
        assert any(r["column"] == "monthly_charges" for r in null_fails)

    def test_null_rate_at_threshold_passes(self):
        df = _make_clean_df(100)
        # Inject exactly 10% NULLs
        df.loc[:9, "monthly_charges"] = None
        config = _make_config(null_rate_threshold=10.0)
        results = run_quality_checks(df, config=config)
        mc_check = [r for r in results if r["check"] == "null_rate" and r["column"] == "monthly_charges"]
        assert len(mc_check) == 1
        assert mc_check[0]["status"] == "PASS"  # 10% is not > 10%

    def test_empty_dataframe_fails(self):
        df = pd.DataFrame(columns=_make_clean_df(1).columns)
        config = _make_config(null_rate_threshold=10.0)
        results = run_quality_checks(df, config=config)
        null_checks = [r for r in results if r["check"] == "null_rate"]
        assert any(r["status"] == "FAIL" for r in null_checks)


class TestDuplicateDetection:
    """Tests for duplicate detection."""

    def test_no_duplicates_passes(self):
        df = _make_clean_df(100)
        config = _make_config(duplicate_threshold=5.0)
        results = run_quality_checks(df, config=config)
        dup_checks = [r for r in results if r["check"] in ("duplicate_rows", "duplicate_ids")]
        assert all(r["status"] == "PASS" for r in dup_checks)

    def test_duplicate_rows_detected(self):
        df = _make_clean_df(100)
        # Add 20 duplicate rows (20% > 5% threshold)
        dups = df.head(20).copy()
        df = pd.concat([df, dups], ignore_index=True)
        config = _make_config(duplicate_threshold=5.0)
        results = run_quality_checks(df, config=config)
        dup_row_checks = [r for r in results if r["check"] == "duplicate_rows"]
        assert any(r["status"] == "FAIL" for r in dup_row_checks)

    def test_duplicate_ids_detected(self):
        df = _make_clean_df(100)
        # Create duplicate IDs
        df.loc[50, "customer_id"] = df.loc[0, "customer_id"]
        config = _make_config(duplicate_threshold=5.0)
        results = run_quality_checks(df, config=config)
        dup_id_checks = [r for r in results if r["check"] == "duplicate_ids"]
        assert any(r["status"] == "FAIL" for r in dup_id_checks)


class TestRowCountAnomaly:
    """Tests for row-count drift detection."""

    def test_stable_count_passes(self):
        df = _make_clean_df(100)
        config = _make_config(row_count_change_threshold=20.0)
        results = run_quality_checks(df, previous_row_count=100, config=config)
        rc_checks = [r for r in results if r["check"] == "row_count"]
        assert all(r["status"] == "PASS" for r in rc_checks)

    def test_large_drop_fails(self):
        df = _make_clean_df(50)  # 50% drop from 100
        config = _make_config(row_count_change_threshold=20.0)
        results = run_quality_checks(df, previous_row_count=100, config=config)
        rc_checks = [r for r in results if r["check"] == "row_count"]
        assert any(r["status"] == "FAIL" for r in rc_checks)

    def test_large_spike_fails(self):
        df = _make_clean_df(200)  # 100% increase from 100
        config = _make_config(row_count_change_threshold=20.0)
        results = run_quality_checks(df, previous_row_count=100, config=config)
        rc_checks = [r for r in results if r["check"] == "row_count"]
        assert any(r["status"] == "FAIL" for r in rc_checks)

    def test_no_previous_count_passes(self):
        df = _make_clean_df(100)
        config = _make_config(row_count_change_threshold=20.0)
        results = run_quality_checks(df, previous_row_count=None, config=config)
        rc_checks = [r for r in results if r["check"] == "row_count"]
        assert all(r["status"] == "PASS" for r in rc_checks)


class TestCategoricalValidity:
    """Tests for categorical value checks."""

    def test_valid_categories_pass(self):
        df = _make_clean_df(100)
        config = _make_config()
        results = run_quality_checks(df, config=config)
        cat_checks = [r for r in results if r["check"] == "categorical_validity"]
        assert all(r["status"] == "PASS" for r in cat_checks)

    def test_unexpected_category_fails(self):
        df = _make_clean_df(100)
        df.loc[0, "contract"] = "Lifetime"  # Invalid category
        config = _make_config()
        results = run_quality_checks(df, config=config)
        contract_check = [
            r for r in results
            if r["check"] == "categorical_validity" and r.get("column") == "contract"
        ]
        assert any(r["status"] == "FAIL" for r in contract_check)


class TestNumericRange:
    """Tests for numeric range checks."""

    def test_valid_ranges_pass(self):
        df = _make_clean_df(100)
        config = _make_config()
        results = run_quality_checks(df, config=config)
        num_checks = [r for r in results if r["check"] == "numeric_range"]
        assert all(r["status"] == "PASS" for r in num_checks)

    def test_negative_charges_fail(self):
        df = _make_clean_df(100)
        df.loc[0, "monthly_charges"] = -50.0  # Out of range
        config = _make_config()
        results = run_quality_checks(df, config=config)
        mc_check = [
            r for r in results
            if r["check"] == "numeric_range" and r.get("column") == "monthly_charges"
        ]
        assert any(r["status"] == "FAIL" for r in mc_check)
