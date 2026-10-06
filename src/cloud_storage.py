"""
src/cloud_storage.py — Supabase Storage upload, download, and listing operations.

Functions:
    upload_file()   — Upload a local file to the Supabase Storage bucket.
    download_file() — Download a file from Supabase to local disk.
    list_files()    — List objects under a given prefix.

All functions include error handling and logging.
Credentials are read from the Config; never hardcoded.
"""

from __future__ import annotations

import os
from typing import Optional

from supabase import create_client, Client

from src.config import Config, get_config
from src.logging_config import get_logger

logger = get_logger(__name__)


def _get_supabase_client(config: Optional[Config] = None) -> Client:
    """Create a Supabase client using the application config."""
    cfg = config or get_config()
    return create_client(cfg.supabase_url, cfg.supabase_key)


def upload_file(
    local_path: str,
    remote_key: str,
    config: Optional[Config] = None,
) -> bool:
    """
    Upload *local_path* to Supabase Storage bucket.

    Returns True on success, False on failure.
    """
    cfg = config or get_config()
    if not cfg.has_storage():
        logger.warning("Supabase Storage not configured — skipping upload of %s", local_path)
        return False

    if not os.path.isfile(local_path):
        logger.error("Local file not found: %s", local_path)
        return False

    try:
        client = _get_supabase_client(cfg)
        logger.info("Uploading %s → Supabase Storage (Bucket: %s, Key: %s)", local_path, cfg.supabase_bucket_name, remote_key)
        
        with open(local_path, 'rb') as f:
            # We use upsert=True to overwrite if it already exists
            client.storage.from_(cfg.supabase_bucket_name).upload(
                file=f,
                path=remote_key,
                file_options={"cacheControl": "3600", "upsert": "true"}
            )
            
        logger.info("Upload complete")
        return True
    except Exception as exc:
        logger.error("Supabase Storage upload failed: %s", exc)
        return False


def download_file(
    remote_key: str,
    local_path: str,
    config: Optional[Config] = None,
) -> bool:
    """
    Download a file from Supabase Storage to *local_path*.

    Creates parent directories if needed.
    Returns True on success, False on failure.
    """
    cfg = config or get_config()
    if not cfg.has_storage():
        logger.warning("Supabase Storage not configured — skipping download of %s", remote_key)
        return False

    try:
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        client = _get_supabase_client(cfg)
        logger.info("Downloading Supabase Storage (Bucket: %s, Key: %s) → %s", cfg.supabase_bucket_name, remote_key, local_path)
        
        with open(local_path, 'wb+') as f:
            res = client.storage.from_(cfg.supabase_bucket_name).download(remote_key)
            f.write(res)
            
        logger.info("Download complete")
        return True
    except Exception as exc:
        logger.error("Supabase Storage download failed: %s", exc)
        return False


def list_files(
    prefix: str = "",
    config: Optional[Config] = None,
) -> list[str]:
    """
    List all object keys under *prefix* in the configured Supabase bucket.

    Returns a list of keys (strings). Returns an empty list on error.
    """
    cfg = config or get_config()
    if not cfg.has_storage():
        logger.warning("Supabase Storage not configured — cannot list files")
        return []

    try:
        client = _get_supabase_client(cfg)
        # We need to strip trailing slashes for Supabase list()
        clean_prefix = prefix.strip("/")
        
        res = client.storage.from_(cfg.supabase_bucket_name).list(clean_prefix)
        
        keys: list[str] = []
        for obj in res:
            # Only add actual files, not directories/placeholders
            if obj.get("id"):
                keys.append(os.path.join(prefix, obj["name"]).replace("\\", "/"))
                
        logger.info("Listed %d objects under prefix '%s'", len(keys), prefix)
        return keys
    except Exception as exc:
        logger.error("Supabase Storage listing failed: %s", exc)
        return []
