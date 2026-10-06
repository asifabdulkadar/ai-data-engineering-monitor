"""
tests/test_schema_validator.py — Unit tests for the schema validator.

Tests:
    - Missing required columns.
    - Unexpected extra columns.
    - Incorrect data types.
    - Valid schemas passing.
"""

import pandas as pd

from src.schema_validator import validate_schema


def test_valid_schema():
    df = pd.DataFrame({
        "customerid":       ["CUST-001"],
        "gender":           ["Female"],
        "seniorcitizen":    [0],
        "partner":          ["Yes"],
        "dependents":       ["No"],
        "tenure":           [12],
        "phoneservice":     ["Yes"],
        "multiplelines":    ["No"],
        "internetservice":  ["DSL"],
        "onlinesecurity":   ["No"],
        "onlinebackup":     ["No"],
        "deviceprotection": ["No"],
        "techsupport":      ["No"],
        "streamingtv":      ["No"],
        "streamingmovies":  ["No"],
        "contract":         ["Month-to-month"],
        "paperlessbilling": ["Yes"],
        "paymentmethod":    ["Electronic check"],
        "monthlycharges":   [55.5],
        "totalcharges":     [666.0],
        "churn":            ["No"],
    })
    
    result = validate_schema(df)
    assert result["status"] == "PASS"
    assert not result["missing_columns"]
    assert not result["unexpected_columns"]
    assert not result["type_mismatches"]


def test_missing_required_column():
    df = pd.DataFrame({
        "customerid":       ["CUST-001"],
        "gender":           ["Female"],
        # "seniorcitizen" is missing
        "partner":          ["Yes"],
        "dependents":       ["No"],
        "tenure":           [12],
        "phoneservice":     ["Yes"],
        "multiplelines":    ["No"],
        "internetservice":  ["DSL"],
        "onlinesecurity":   ["No"],
        "onlinebackup":     ["No"],
        "deviceprotection": ["No"],
        "techsupport":      ["No"],
        "streamingtv":      ["No"],
        "streamingmovies":  ["No"],
        "contract":         ["Month-to-month"],
        "paperlessbilling": ["Yes"],
        "paymentmethod":    ["Electronic check"],
        "monthlycharges":   [55.5],
        "totalcharges":     [666.0],
        "churn":            ["No"],
    })
    
    result = validate_schema(df)
    assert result["status"] == "FAIL"
    assert "seniorcitizen" in result["missing_columns"]


def test_unexpected_column():
    df = pd.DataFrame({
        "customerid":       ["CUST-001"],
        "gender":           ["Female"],
        "seniorcitizen":    [0],
        "partner":          ["Yes"],
        "dependents":       ["No"],
        "tenure":           [12],
        "phoneservice":     ["Yes"],
        "multiplelines":    ["No"],
        "internetservice":  ["DSL"],
        "onlinesecurity":   ["No"],
        "onlinebackup":     ["No"],
        "deviceprotection": ["No"],
        "techsupport":      ["No"],
        "streamingtv":      ["No"],
        "streamingmovies":  ["No"],
        "contract":         ["Month-to-month"],
        "paperlessbilling": ["Yes"],
        "paymentmethod":    ["Electronic check"],
        "monthlycharges":   [55.5],
        "totalcharges":     [666.0],
        "churn":            ["No"],
        "extra_column":     ["Whoops"],  # Unexpected
    })
    
    result = validate_schema(df)
    assert result["status"] == "WARN"  # Extra columns only cause a WARN
    assert "extra_column" in result["unexpected_columns"]


def test_type_mismatch():
    df = pd.DataFrame({
        "customerid":       ["CUST-001"],
        "gender":           ["Female"],
        "seniorcitizen":    [0],
        "partner":          ["Yes"],
        "dependents":       ["No"],
        "tenure":           ["Twelve"],  # String instead of int
        "phoneservice":     ["Yes"],
        "multiplelines":    ["No"],
        "internetservice":  ["DSL"],
        "onlinesecurity":   ["No"],
        "onlinebackup":     ["No"],
        "deviceprotection": ["No"],
        "techsupport":      ["No"],
        "streamingtv":      ["No"],
        "streamingmovies":  ["No"],
        "contract":         ["Month-to-month"],
        "paperlessbilling": ["Yes"],
        "paymentmethod":    ["Electronic check"],
        "monthlycharges":   [55.5],
        "totalcharges":     [666.0],
        "churn":            ["No"],
    })
    
    result = validate_schema(df)
    assert result["status"] == "FAIL"
    assert any(m["column"] == "tenure" for m in result["type_mismatches"])
