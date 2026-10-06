"""
app.py — Streamlit Dashboard for AI Data Engineering Monitoring Agent.

Title: AI Data Engineering Monitoring Agent

Sections:
    1. Pipeline Overview — status, rows, timing
    2. Data Quality — NULL rates, duplicates, schema, freshness
    3. Anomalies — table of detected anomalies
    4. AI Incident Report — interpretation, causes, actions
    5. Pipeline Simulation — buttons to simulate failures and run monitoring

Deployment:
    - Local: streamlit run app.py
    - Cloud: Streamlit Community Cloud (reads from st.secrets)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, Optional

import streamlit as st
import pandas as pd

# ---------------------------------------------------------------------------
# Bridge Streamlit secrets → environment variables (for cloud deployment)
# ---------------------------------------------------------------------------
try:
    if hasattr(st, "secrets"):
        for key in (
            "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_BUCKET_NAME",
            "DATABASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL",
            "ROW_COUNT_CHANGE_THRESHOLD", "NULL_RATE_THRESHOLD", "DUPLICATE_THRESHOLD",
        ):
            if key in st.secrets:
                os.environ[key] = str(st.secrets[key])
except Exception:
    pass  # Secrets not available (local dev uses .env)

from src.config import get_config
from src.logging_config import setup_logging
from src.monitoring import run_monitoring, MonitoringResult

setup_logging()

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Data Engineering Monitor",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Authentication (Optional Login Portal)
# ---------------------------------------------------------------------------
if hasattr(st, "secrets") and "APP_PASSWORD" in st.secrets:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        
    if not st.session_state.authenticated:
        st.title("🔒 Login Required")
        st.markdown("This dashboard is password protected.")
        pwd = st.text_input("Enter Dashboard Password", type="password")
        if st.button("Login"):
            if pwd == str(st.secrets["APP_PASSWORD"]):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password")
        st.stop()

# ---------------------------------------------------------------------------
# Custom CSS for a clean professional look
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .block-container { padding-top: 1rem; }
    .stMetric { background: #f8f9fa; border-radius: 8px; padding: 12px; }
    .status-healthy { color: #28a745; font-weight: bold; }
    .status-failed  { color: #dc3545; font-weight: bold; }
    .status-degraded { color: #ffc107; font-weight: bold; }
    div[data-testid="stExpander"] { border: 1px solid #e0e0e0; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("🔍 AI Data Monitor")
st.sidebar.markdown("**Cloud-hosted MVP / portfolio project**")
st.sidebar.markdown("---")

config = get_config()
st.sidebar.markdown("### Configuration")
st.sidebar.text(f"Pipeline: {config.pipeline_name}")
st.sidebar.text(f"Storage: {'✅ Configured' if config.has_storage() else '❌ Not configured'}")
st.sidebar.text(f"Database: {'✅ Configured' if config.database_url else '❌ Not configured'}")
st.sidebar.text(f"OpenAI: {'✅ Configured' if config.has_openai() else '❌ Not configured'}")
st.sidebar.text(f"Thresholds: RowΔ={config.row_count_change_threshold}%, "
                f"Null={config.null_rate_threshold}%, Dup={config.duplicate_threshold}%")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "monitoring_result" not in st.session_state:
    st.session_state.monitoring_result: Optional[MonitoringResult] = None


def _status_emoji(status: str) -> str:
    return {"HEALTHY": "🟢", "DEGRADED": "🟡", "FAILED": "🔴", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(status, "⚪")


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
st.title("🤖 AI Data Engineering Monitoring Agent")
st.caption("End-to-end data pipeline monitoring with deterministic quality checks and AI-powered incident analysis")

# ==============================
# Section 5: Pipeline Simulation (at top for UX — run first, see results below)
# ==============================
st.markdown("---")
st.header("🎮 Pipeline Simulation")

sim_col1, sim_col2, sim_col3, sim_col4, sim_col5 = st.columns(5)
simulated_file: Optional[str] = None

raw_path = config.raw_data_path
skip_db = not bool(config.database_url)
skip_storage = not config.has_storage()


def _simulate(sim_type: str) -> Optional[str]:
    """Run the failure simulator and return the corrupted file path."""
    output_file = os.path.join("data", "raw", f"corrupted_{sim_type}.csv")
    try:
        subprocess.run(
            [sys.executable, "simulate_failure.py", "--type", sim_type, "--input", raw_path],
            check=True, capture_output=True, text=True,
        )
        return output_file
    except subprocess.CalledProcessError as e:
        st.error(f"Simulation failed: {e.stderr}")
        return None
    except FileNotFoundError:
        st.error(f"Original dataset not found at {raw_path}. Please download it first.")
        return None


with sim_col1:
    if st.button("💉 Simulate NULLs", use_container_width=True):
        simulated_file = _simulate("nulls")
with sim_col2:
    if st.button("📋 Simulate Duplicates", use_container_width=True):
        simulated_file = _simulate("duplicates")
with sim_col3:
    if st.button("📉 Simulate Row Loss", use_container_width=True):
        simulated_file = _simulate("row_loss")
with sim_col4:
    if st.button("🔧 Simulate Schema Fail", use_container_width=True):
        simulated_file = _simulate("schema_change")
with sim_col5:
    if st.button("🚀 Run Clean Pipeline", use_container_width=True):
        simulated_file = None  # Use original

# Determine which file to use
pipeline_file = simulated_file if simulated_file else raw_path

# Run monitoring button
run_col1, run_col2 = st.columns([1, 3])
with run_col1:
    run_clicked = st.button("▶️ **Run Monitoring**", type="primary", use_container_width=True)
with run_col2:
    st.info(f"Dataset: `{pipeline_file}` | DB: {'✅' if not skip_db else '⏭️ skip'} | Storage: {'✅' if not skip_storage else '⏭️ skip'}")

if run_clicked:
    with st.spinner("Running pipeline and monitoring..."):
        try:
            result = run_monitoring(
                file_path=pipeline_file,
                config=config,
                skip_storage=skip_storage,
                skip_db=skip_db,
            )
            st.session_state.monitoring_result = result
            st.success(f"Pipeline complete — Status: {_status_emoji(result.overall_status)} {result.overall_status}")
        except Exception as exc:
            st.error(f"Pipeline error: {exc}")

# ==============================
# Display results from session state
# ==============================
result = st.session_state.monitoring_result

if result is None:
    st.markdown("---")
    st.info("👆 Click **Run Monitoring** above to execute the pipeline and see results.")
    st.stop()

# ==============================
# Section 1: Pipeline Overview
# ==============================
st.markdown("---")
st.header(f"📊 Pipeline Overview {_status_emoji(result.overall_status)}")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Status", result.overall_status)
m2.metric("Rows Received", f"{result.rows_received:,}")
m3.metric("Rows Processed", f"{result.rows_processed:,}")
m4.metric("Rows Rejected", f"{result.rows_rejected:,}")

if result.start_time and result.end_time:
    duration = (result.end_time - result.start_time).total_seconds()
    m5.metric("Duration", f"{duration:.1f}s")
else:
    m5.metric("Duration", "N/A")

if result.error_message:
    st.error(f"**Error:** {result.error_message}")


# ==============================
# Section 2: Data Quality
# ==============================
st.markdown("---")
st.header("🔬 Data Quality")

if result.quality_results:
    # Summary metrics
    qr = result.quality_results
    fails = sum(1 for r in qr if r["status"] == "FAIL")
    passes = sum(1 for r in qr if r["status"] == "PASS")
    warns = sum(1 for r in qr if r["status"] == "WARN")

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Total Checks", len(qr))
    q2.metric("Passed ✅", passes)
    q3.metric("Failed ❌", fails)
    q4.metric("Warnings ⚠️", warns)

    # Group checks by type
    check_types = sorted(set(r["check"] for r in qr))

    for check_type in check_types:
        checks = [r for r in qr if r["check"] == check_type]
        any_fail = any(c["status"] == "FAIL" for c in checks)
        icon = "❌" if any_fail else "✅"

        with st.expander(f"{icon} {check_type.replace('_', ' ').title()} ({len(checks)} checks)"):
            # Show only failed/warning checks by default, all if expanded
            display_checks = [c for c in checks if c["status"] in ("FAIL", "WARN")]
            if not display_checks:
                display_checks = checks[:5]  # Show first 5 passing checks

            df_checks = pd.DataFrame(display_checks)
            cols_to_show = ["check", "column", "status", "severity", "actual", "threshold", "message"]
            cols_available = [c for c in cols_to_show if c in df_checks.columns]
            st.dataframe(df_checks[cols_available], use_container_width=True, hide_index=True)
else:
    st.info("No quality check results available yet.")


# ==============================
# Section 3: Anomalies
# ==============================
st.markdown("---")
st.header("⚠️ Anomalies")

if result.anomalies:
    st.warning(f"**{len(result.anomalies)} anomaly(ies) detected**")
    anomaly_data = []
    for a in result.anomalies:
        anomaly_data.append({
            "Type": a.get("anomaly_type", ""),
            "Severity": a.get("severity", ""),
            "Description": a.get("description", ""),
        })
    st.dataframe(pd.DataFrame(anomaly_data), use_container_width=True, hide_index=True)
else:
    st.success("✅ No anomalies detected")


# ==============================
# Section 4: AI Incident Report
# ==============================
st.markdown("---")
st.header("🤖 AI Incident Report")

report = result.incident_report
if report:
    ai_available = report.get("ai_available", False)

    if not ai_available:
        st.warning("⚠️ AI analysis unavailable. Deterministic monitoring results are still available above.")

    severity = report.get("severity", "NONE")
    severity_colors = {"NONE": "green", "LOW": "blue", "MEDIUM": "orange", "HIGH": "red", "CRITICAL": "red"}
    sev_color = severity_colors.get(severity, "grey")

    r1, r2, r3 = st.columns(3)
    r1.metric("Incident", report.get("incident_title", "N/A"))
    r2.metric("Severity", severity)
    r3.metric("Confidence", f"{report.get('confidence', 0):.0%}")

    st.markdown(f"**Summary:** {report.get('summary', 'N/A')}")

    col_left, col_right = st.columns(2)

    with col_left:
        with st.expander("📋 Confirmed Facts", expanded=True):
            facts = report.get("confirmed_facts", [])
            if facts:
                for fact in facts:
                    st.markdown(f"- {fact}")
            else:
                st.markdown("*None*")

        with st.expander("💼 Business Impact"):
            st.markdown(report.get("business_impact", "N/A"))

    with col_right:
        with st.expander("🔍 Possible Root Causes", expanded=True):
            causes = report.get("possible_root_causes", [])
            if causes:
                for cause in causes:
                    st.markdown(f"- {cause}")
            else:
                st.markdown("*None*")

        with st.expander("🛠️ Recommended Actions"):
            actions = report.get("recommended_actions", [])
            if actions:
                for action in actions:
                    st.markdown(f"- {action}")
            else:
                st.markdown("*None*")
else:
    st.info("No incident report available yet. Run the pipeline to generate one.")


# ==============================
# Footer
# ==============================
st.markdown("---")
st.caption("AI Data Engineering Monitoring Agent — Cloud-hosted MVP / Portfolio Project")
