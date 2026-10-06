"""
src/etl.py — ETL (Extract–Transform–Load) pipeline.

Pipeline stages:
    Raw CSV → Load → Clean → Normalize → Validate → Transform → Load PostgreSQL

Tracks rows_received, rows_processed, rows_rejected.
Never silently discards bad data — all rejected rows are counted and logged.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from src.config import Config, get_config
from src.database import get_connection, insert_dataframe
from src.ingestion import ingest_csv
from src.logging_config import get_logger
from src.schema_validator import validate_schema
from src.cloud_storage import upload_file
from sqlalchemy import text

logger = get_logger(__name__)


def _clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Clean the DataFrame:
        - Strip whitespace from string columns.
        - Convert TotalCharges from string to numeric.
        - Handle blanks in TotalCharges (new customers with tenure=0).
        - Remove exact duplicate rows (keep first).

    Returns (cleaned_df, rejected_count).
    """
    rejected = 0
    original_len = len(df)

    # Strip whitespace from all object columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].str.strip()

    # TotalCharges: the raw data has blank strings for some new customers
    if "totalcharges" in df.columns:
        # Replace blank strings with NaN, then convert to float
        df["totalcharges"] = pd.to_numeric(df["totalcharges"], errors="coerce")
        blanks = df["totalcharges"].isna().sum()
        if blanks > 0:
            logger.info("TotalCharges: %d blank values converted to NaN (new customers with tenure=0)", blanks)
            # Fill NaN with 0.0 for new customers
            df["totalcharges"] = df["totalcharges"].fillna(0.0)

    # Remove exact duplicate rows
    dup_mask = df.duplicated(keep="first")
    dup_count = dup_mask.sum()
    if dup_count > 0:
        logger.warning("Removing %d exact duplicate rows", dup_count)
        df = df[~dup_mask].copy()
        rejected += dup_count

    logger.info("Cleaning complete: %d → %d rows (%d rejected)", original_len, len(df), rejected)
    return df, rejected


def _normalize_categories(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize categorical values: consistent casing and labels."""
    # Standardise Yes/No columns
    yes_no_cols = ["partner", "dependents", "phoneservice", "paperlessbilling", "churn"]
    for col in yes_no_cols:
        if col in df.columns:
            df[col] = df[col].str.capitalize()

    # Standardise gender
    if "gender" in df.columns:
        df["gender"] = df["gender"].str.capitalize()

    return df


def _transform_types(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure correct data types after cleaning."""
    type_map = {
        "seniorcitizen": "int64",
        "tenure": "int64",
        "monthlycharges": "float64",
        "totalcharges": "float64",
    }
    for col, dtype in type_map.items():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(dtype)
    return df


def _rename_for_db(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns from the ingested snake_case to the DB column names."""
    rename_map = {
        "customerid":       "customer_id",
        "seniorcitizen":    "senior_citizen",
        "phoneservice":     "phone_service",
        "multiplelines":    "multiple_lines",
        "internetservice":  "internet_service",
        "onlinesecurity":   "online_security",
        "onlinebackup":     "online_backup",
        "deviceprotection": "device_protection",
        "techsupport":      "tech_support",
        "streamingtv":      "streaming_tv",
        "streamingmovies":  "streaming_movies",
        "paperlessbilling": "paperless_billing",
        "paymentmethod":    "payment_method",
        "monthlycharges":   "monthly_charges",
        "totalcharges":     "total_charges",
    }
    df = df.rename(columns=rename_map)
    return df


def run_etl(
    file_path: Optional[str] = None,
    config: Optional[Config] = None,
    skip_storage: bool = False,
    skip_db: bool = False,
) -> dict[str, Any]:
    """
    Execute the full ETL pipeline.

    Returns a result dict:
        {
            "run_id": str,
            "pipeline_name": str,
            "status": "SUCCESS" | "FAILED",
            "rows_received": int,
            "rows_processed": int,
            "rows_rejected": int,
            "start_time": datetime,
            "end_time": datetime,
            "schema_result": dict,
            "error_message": str | None,
            "dataframe": pd.DataFrame,  # the cleaned/transformed data
        }
    """
    cfg = config or get_config()
    run_id = str(uuid.uuid4())
    start_time = datetime.now(timezone.utc)
    path = file_path or cfg.raw_data_path

    result: dict[str, Any] = {
        "run_id": run_id,
        "pipeline_name": cfg.pipeline_name,
        "status": "RUNNING",
        "rows_received": 0,
        "rows_processed": 0,
        "rows_rejected": 0,
        "start_time": start_time,
        "end_time": None,
        "schema_result": {},
        "error_message": None,
        "dataframe": pd.DataFrame(),
    }

    try:
        # --- EXTRACT ---
        logger.info("=" * 50)
        logger.info("ETL Pipeline started — run_id=%s", run_id)
        logger.info("=" * 50)

        # Upload raw file to S3 (optional)
        if not skip_storage and cfg.has_storage():
            remote_key = f"raw/{run_id}/WA_Fn-UseC_-Telco-Customer-Churn.csv"
            upload_file(path, remote_key, cfg)

        df = ingest_csv(path)
        result["rows_received"] = len(df)

        # (Validation moved to after initial transform)

        # --- TRANSFORM ---
        df, rejected = _clean_dataframe(df)
        df = _normalize_categories(df)
        df = _transform_types(df)

        df = _rename_for_db(df)
        
        # --- VALIDATE ---
        schema_result = validate_schema(df)
        result["schema_result"] = schema_result
        if schema_result["status"] == "FAIL":
            raise ValueError(f"Schema validation failed: {schema_result['message']}")

        result["rows_rejected"] = rejected
        result["rows_processed"] = len(df)
        result["dataframe"] = df

        # --- LOAD ---
        if not skip_db:
            # Upload processed file to S3 (optional)
            if cfg.has_storage():
                import os
                processed_path = f"data/processed/{run_id}_customers.csv"
                os.makedirs(os.path.dirname(processed_path), exist_ok=True)
                df.to_csv(processed_path, index=False)
                upload_file(processed_path, f"processed/{run_id}/customers.csv", cfg)

            # Load into PostgreSQL (idempotent: replace entire table)
            insert_dataframe(df, "customers", if_exists="replace", config=cfg)

            # Record the pipeline run
            _record_pipeline_run(result, cfg)

        result["status"] = "SUCCESS"
        logger.info("ETL Pipeline completed successfully — %d rows processed", len(df))

    except Exception as exc:
        result["status"] = "FAILED"
        result["error_message"] = str(exc)
        logger.error("ETL Pipeline FAILED: %s", exc)
        # Still try to record the failed run
        if not skip_db:
            try:
                _record_pipeline_run(result, cfg)
            except Exception as db_err:
                logger.error("Could not record failed run: %s", db_err)

    result["end_time"] = datetime.now(timezone.utc)
    return result


def _record_pipeline_run(result: dict[str, Any], config: Config) -> None:
    """Insert a row into pipeline_runs."""
    sql = """
        INSERT INTO pipeline_runs (run_id, pipeline_name, start_time, end_time,
                                   status, rows_received, rows_processed,
                                   rows_rejected, error_message)
        VALUES (:run_id, :pipeline_name, :start_time, :end_time,
                :status, :rows_received, :rows_processed,
                :rows_rejected, :error_message)
        ON CONFLICT (run_id) DO UPDATE SET
            end_time       = EXCLUDED.end_time,
            status         = EXCLUDED.status,
            rows_received  = EXCLUDED.rows_received,
            rows_processed = EXCLUDED.rows_processed,
            rows_rejected  = EXCLUDED.rows_rejected,
            error_message  = EXCLUDED.error_message
    """
    with get_connection(config) as conn:
        conn.execute(text(sql), {
            "run_id":          result["run_id"],
            "pipeline_name":   result["pipeline_name"],
            "start_time":      result["start_time"],
            "end_time":        result.get("end_time"),
            "status":          result["status"],
            "rows_received":   result["rows_received"],
            "rows_processed":  result["rows_processed"],
            "rows_rejected":   result["rows_rejected"],
            "error_message":   result.get("error_message"),
        })
    logger.info("Pipeline run recorded: %s [%s]", result["run_id"], result["status"])
