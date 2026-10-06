#!/usr/bin/env python3
"""
run_pipeline.py — CLI entry point for the full monitoring pipeline.

Usage:
    python run_pipeline.py
    python run_pipeline.py --file data/raw/corrupted.csv
    python run_pipeline.py --skip-storage
    python run_pipeline.py --skip-db   # dry-run (no database)

Executes:
    1. Load configuration
    2. Read raw data
    3. Upload to Supabase Storage (if configured)
    4. Validate schema
    5. Transform data
    6. Load PostgreSQL
    7. Run quality checks
    8. Detect anomalies
    9. Persist monitoring results
   10. Call AI agent if anomalies exist
   11. Store incident report
   12. Print final summary
"""

from __future__ import annotations

import argparse
import sys

from src.config import get_config
from src.database import init_schema
from src.logging_config import setup_logging
from src.monitoring import run_monitoring, print_summary


def main() -> int:
    """Run the full pipeline and return exit code (0=healthy, 1=anomaly, 2=error)."""
    parser = argparse.ArgumentParser(description="AI Data Engineering Monitor — Pipeline Runner")
    parser.add_argument(
        "--file", type=str, default=None,
        help="Path to CSV file (default: data/raw/WA_Fn-UseC_-Telco-Customer-Churn.csv)",
    )
    parser.add_argument("--skip-storage", action="store_true", help="Skip Supabase Storage upload/download")
    parser.add_argument("--skip-db", action="store_true", help="Skip database operations (dry run)")
    parser.add_argument("--init-db", action="store_true", help="Initialise database schema before running")
    args = parser.parse_args()

    setup_logging()
    config = get_config()

    # Validate minimal config
    if not args.skip_db:
        issues = config.validate()
        if issues:
            print(f"Configuration errors: {issues}")
            print("Set the required environment variables or use --skip-db for a dry run.")
            return 2

    # Initialise database schema if requested
    if args.init_db and not args.skip_db:
        try:
            init_schema(config)
            print("Database schema initialised successfully.")
        except Exception as exc:
            print(f"Failed to initialise schema: {exc}")
            return 2

    # Run monitoring
    result = run_monitoring(
        file_path=args.file,
        config=config,
        skip_storage=args.skip_storage,
        skip_db=args.skip_db,
    )

    # Print summary
    print_summary(result)

    # Exit code
    if result.overall_status == "HEALTHY":
        return 0
    elif result.overall_status == "FAILED":
        return 1
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
