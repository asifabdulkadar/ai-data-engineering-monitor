"""
src/ingestion.py — Raw data ingestion from CSV.

Responsibilities:
    1. Validate the CSV file exists.
    2. Read it into a Pandas DataFrame.
    3. Normalise column names (lowercase, underscores).
    4. Report row count.
    5. Detect missing required columns.
    6. Return the DataFrame.
"""

from __future__ import annotations

import os
import re

import pandas as pd

from src.logging_config import get_logger

logger = get_logger(__name__)

# Columns expected in the Telco Customer Churn dataset
REQUIRED_COLUMNS: list[str] = [
    "customerid",
    "gender",
    "seniorcitizen",
    "partner",
    "dependents",
    "tenure",
    "phoneservice",
    "multiplelines",
    "internetservice",
    "onlinesecurity",
    "onlinebackup",
    "deviceprotection",
    "techsupport",
    "streamingtv",
    "streamingmovies",
    "contract",
    "paperlessbilling",
    "paymentmethod",
    "monthlycharges",
    "totalcharges",
    "churn",
]


def _normalise_column_name(col: str) -> str:
    """Convert column name to snake_case: lowercase, spaces→underscores, strip punctuation."""
    col = col.strip().lower()
    col = re.sub(r"[^a-z0-9]+", "_", col)
    return col.strip("_")


def ingest_csv(file_path: str) -> pd.DataFrame:
    """
    Read the raw CSV and return a normalised DataFrame.

    Raises FileNotFoundError if the file does not exist.
    Raises ValueError if required columns are missing.
    """
    # 1. Validate file exists
    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"Dataset not found: {file_path}. "
            "Download the Telco Customer Churn dataset from Kaggle and place it in data/raw/"
        )

    logger.info("Reading CSV: %s", file_path)
    df = pd.read_csv(file_path)
    logger.info("Raw rows: %d, columns: %d", len(df), len(df.columns))

    # 3. Normalise column names
    df.columns = [_normalise_column_name(c) for c in df.columns]
    logger.info("Normalised columns: %s", list(df.columns))

    # 4. Row count
    logger.info("Rows ingested: %d", len(df))

    # 5. Detect missing required columns
    current_cols = set(df.columns)
    missing = [c for c in REQUIRED_COLUMNS if c not in current_cols]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    return df
