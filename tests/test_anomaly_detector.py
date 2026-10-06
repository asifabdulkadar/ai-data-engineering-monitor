"""
tests/test_anomaly_detector.py — Unit tests for the anomaly detector.

Tests:
    - Row-count anomalies (drops and spikes).
    - Null-rate anomalies.
    - Schema anomalies.
"""

from src.anomaly_detector import detect_anomalies
from src.config import Config


def _make_config() -> Config:
    import os
    os.environ["ROW_COUNT_CHANGE_THRESHOLD"] = "20.0"
    os.environ["NULL_RATE_THRESHOLD"] = "10.0"
    os.environ["DUPLICATE_THRESHOLD"] = "5.0"
    return Config()


def test_row_count_drop_detected():
    quality_results = []
    etl_result = {"rows_processed": 50}  # Dropped from 100
    previous_count = 100
    config = _make_config()
    
    anomalies = detect_anomalies(quality_results, etl_result, previous_count, config)
    
    drop_anomalies = [a for a in anomalies if a["anomaly_type"] == "row_count_drop"]
    assert len(drop_anomalies) == 1
    assert drop_anomalies[0]["severity"] == "HIGH"
    assert drop_anomalies[0]["details"]["change_pct"] == -50.0


def test_row_count_spike_detected():
    quality_results = []
    etl_result = {"rows_processed": 150}  # Spiked from 100
    previous_count = 100
    config = _make_config()
    
    anomalies = detect_anomalies(quality_results, etl_result, previous_count, config)
    
    spike_anomalies = [a for a in anomalies if a["anomaly_type"] == "row_count_spike"]
    assert len(spike_anomalies) == 1
    assert spike_anomalies[0]["severity"] == "MEDIUM"
    assert spike_anomalies[0]["details"]["change_pct"] == 50.0


def test_null_spike_detected():
    quality_results = [
        {
            "check": "null_rate",
            "column": "total_charges",
            "status": "FAIL",
            "severity": "HIGH",
            "actual": 15.0,
            "threshold": 10.0,
            "message": "NULL rate 15.0% exceeds threshold 10.0%",
        }
    ]
    etl_result = {"rows_processed": 100}
    previous_count = 100
    config = _make_config()
    
    anomalies = detect_anomalies(quality_results, etl_result, previous_count, config)
    
    null_anomalies = [a for a in anomalies if a["anomaly_type"] == "null_rate_spike"]
    assert len(null_anomalies) == 1
    assert null_anomalies[0]["severity"] == "HIGH"
    assert null_anomalies[0]["details"]["column"] == "total_charges"


def test_schema_change_detected():
    quality_results = [
        {
            "check": "schema",
            "column": None,
            "status": "FAIL",
            "severity": "CRITICAL",
            "actual": {"missing_columns": ["total_charges"]},
            "threshold": "Expected schema",
            "message": "Required column(s) missing: ['total_charges']",
        }
    ]
    etl_result = {"rows_processed": 100}
    previous_count = 100
    config = _make_config()
    
    anomalies = detect_anomalies(quality_results, etl_result, previous_count, config)
    
    schema_anomalies = [a for a in anomalies if a["anomaly_type"] == "schema_change"]
    assert len(schema_anomalies) == 1
    assert schema_anomalies[0]["severity"] == "CRITICAL"


def test_healthy_no_anomalies():
    quality_results = [
        {
            "check": "null_rate",
            "column": "total_charges",
            "status": "PASS",
            "severity": "LOW",
            "actual": 5.0,
            "threshold": 10.0,
            "message": "NULL rate 5.0% within threshold",
        }
    ]
    etl_result = {"rows_processed": 100}
    previous_count = 100
    config = _make_config()
    
    anomalies = detect_anomalies(quality_results, etl_result, previous_count, config)
    assert len(anomalies) == 0
