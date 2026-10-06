"""
src/config.py — Centralised configuration management.

Loads all settings from environment variables (.env file for local dev,
Streamlit secrets or OS env vars for cloud). Every module imports config
values from here so credentials are never hardcoded.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env file if it exists (local development).
# In Streamlit Cloud the variables come from st.secrets → os.environ bridge
# configured in app.py.
load_dotenv()


@dataclass(frozen=True)
class Config:
    """Immutable application configuration."""

    # --- Supabase (Database & Storage) ---
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_key: str = field(default_factory=lambda: os.getenv("SUPABASE_KEY", ""))
    supabase_bucket_name: str = field(default_factory=lambda: os.getenv("SUPABASE_BUCKET_NAME", "data-monitor"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    # --- OpenAI ---
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    # --- Thresholds ---
    row_count_change_threshold: float = field(
        default_factory=lambda: float(os.getenv("ROW_COUNT_CHANGE_THRESHOLD", "20"))
    )
    null_rate_threshold: float = field(
        default_factory=lambda: float(os.getenv("NULL_RATE_THRESHOLD", "10"))
    )
    duplicate_threshold: float = field(
        default_factory=lambda: float(os.getenv("DUPLICATE_THRESHOLD", "5"))
    )

    # --- Application ---
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    pipeline_name: str = field(default_factory=lambda: os.getenv("PIPELINE_NAME", "customer_etl"))

    # --- Paths ---
    raw_data_path: str = field(
        default_factory=lambda: os.getenv(
            "RAW_DATA_PATH", os.path.join("data", "raw", "WA_Fn-UseC_-Telco-Customer-Churn.csv")
        )
    )

    def validate(self) -> list[str]:
        """Return a list of missing required settings."""
        issues: list[str] = []
        if not self.database_url:
            issues.append("DATABASE_URL is not set")
        return issues

    def has_storage(self) -> bool:
        """Return True if Supabase Storage credentials are configured."""
        return bool(self.supabase_url and self.supabase_key and self.supabase_bucket_name)

    def has_openai(self) -> bool:
        """Return True if OpenAI is configured."""
        return bool(self.openai_api_key)


def get_config() -> Config:
    """Factory that returns a fresh Config reading current env vars."""
    return Config()
