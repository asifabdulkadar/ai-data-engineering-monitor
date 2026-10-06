#!/usr/bin/env python3
"""
simulate_failure.py — Pipeline failure simulator.

Creates a CORRUPTED COPY of the dataset for testing the monitoring pipeline.
NEVER modifies the original raw dataset.

Supported simulations:
    --type nulls          Inject random NULL values
    --type duplicates     Add duplicate records
    --type row_loss       Delete ~40% of rows
    --type schema_change  Remove a required column
    --type bad_types      Corrupt numeric columns with strings
    --type bad_category   Inject unexpected category values
    --type all            Apply all corruptions at once

Usage:
    python simulate_failure.py --type nulls
    python simulate_failure.py --type duplicates
    python simulate_failure.py --type all
    python simulate_failure.py --type nulls --input data/raw/WA_Fn-UseC_-Telco-Customer-Churn.csv

The corrupted file is written to:
    data/raw/corrupted_<type>.csv
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

DEFAULT_INPUT = os.path.join("data", "raw", "WA_Fn-UseC_-Telco-Customer-Churn.csv")
OUTPUT_DIR = os.path.join("data", "raw")


def _load_original(input_path: str) -> pd.DataFrame:
    """Load the original dataset."""
    if not os.path.isfile(input_path):
        print(f"ERROR: Original dataset not found: {input_path}")
        print("Download the Telco Customer Churn dataset from Kaggle first.")
        sys.exit(1)
    return pd.read_csv(input_path)


def inject_nulls(df: pd.DataFrame, fraction: float = 0.25) -> pd.DataFrame:
    """Randomly set ~25% of values to NaN across multiple columns."""
    df = df.copy()
    np.random.seed(42)
    columns_to_corrupt = ["TotalCharges", "MonthlyCharges", "tenure", "Contract", "gender"]
    for col in columns_to_corrupt:
        if col in df.columns:
            mask = np.random.random(len(df)) < fraction
            df.loc[mask, col] = np.nan
    print(f"  Injected NULLs into {len(columns_to_corrupt)} columns ({fraction*100:.0f}% rate)")
    return df


def inject_duplicates(df: pd.DataFrame, count: int = 1500) -> pd.DataFrame:
    """Append duplicate rows sampled from the existing data."""
    df = df.copy()
    np.random.seed(42)
    duplicates = df.sample(n=min(count, len(df)), replace=True, random_state=42)
    df = pd.concat([df, duplicates], ignore_index=True)
    print(f"  Added {count} duplicate rows (total: {len(df)})")
    return df


def inject_row_loss(df: pd.DataFrame, keep_fraction: float = 0.6) -> pd.DataFrame:
    """Delete ~40% of rows to simulate incomplete ingestion."""
    df = df.copy()
    np.random.seed(42)
    df = df.sample(frac=keep_fraction, random_state=42).reset_index(drop=True)
    print(f"  Reduced to {len(df)} rows ({keep_fraction*100:.0f}% kept)")
    return df


def inject_schema_change(df: pd.DataFrame) -> pd.DataFrame:
    """Remove required columns to simulate a schema change."""
    df = df.copy()
    columns_to_drop = ["TotalCharges", "Churn"]
    for col in columns_to_drop:
        if col in df.columns:
            df = df.drop(columns=[col])
    print(f"  Removed columns: {columns_to_drop}")
    return df


def inject_bad_types(df: pd.DataFrame) -> pd.DataFrame:
    """Corrupt numeric columns with string values."""
    df = df.copy()
    np.random.seed(42)
    if "MonthlyCharges" in df.columns:
        mask = np.random.random(len(df)) < 0.15
        df.loc[mask, "MonthlyCharges"] = "INVALID"
    if "tenure" in df.columns:
        mask = np.random.random(len(df)) < 0.10
        df.loc[mask, "tenure"] = "N/A"
    print("  Corrupted MonthlyCharges and tenure with string values")
    return df


def inject_bad_category(df: pd.DataFrame) -> pd.DataFrame:
    """Inject unexpected category values."""
    df = df.copy()
    np.random.seed(42)
    if "Contract" in df.columns:
        mask = np.random.random(len(df)) < 0.10
        df.loc[mask, "Contract"] = "Lifetime"
    if "gender" in df.columns:
        mask = np.random.random(len(df)) < 0.05
        df.loc[mask, "gender"] = "Unknown"
    if "PaymentMethod" in df.columns:
        mask = np.random.random(len(df)) < 0.08
        df.loc[mask, "PaymentMethod"] = "Cryptocurrency"
    print("  Injected unexpected categories: Lifetime, Unknown, Cryptocurrency")
    return df


SIMULATORS = {
    "nulls":         inject_nulls,
    "duplicates":    inject_duplicates,
    "row_loss":      inject_row_loss,
    "schema_change": inject_schema_change,
    "bad_types":     inject_bad_types,
    "bad_category":  inject_bad_category,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline Failure Simulator")
    parser.add_argument(
        "--type", required=True,
        choices=list(SIMULATORS.keys()) + ["all"],
        help="Type of failure to simulate",
    )
    parser.add_argument(
        "--input", default=DEFAULT_INPUT,
        help=f"Path to original CSV (default: {DEFAULT_INPUT})",
    )
    args = parser.parse_args()

    df = _load_original(args.input)
    print(f"\nOriginal dataset: {len(df)} rows, {len(df.columns)} columns")

    if args.type == "all":
        # Apply all corruptions
        for name, fn in SIMULATORS.items():
            df = fn(df)
        output_file = os.path.join(OUTPUT_DIR, "corrupted_all.csv")
    else:
        fn = SIMULATORS[args.type]
        df = fn(df)
        output_file = os.path.join(OUTPUT_DIR, f"corrupted_{args.type}.csv")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df.to_csv(output_file, index=False)
    print(f"\nCorrupted dataset saved to: {output_file}")
    print(f"Rows: {len(df)}, Columns: {len(df.columns)}")
    print(f"\nRun the pipeline with: python run_pipeline.py --file {output_file}")


if __name__ == "__main__":
    main()
