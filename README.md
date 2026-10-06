# AI-Powered Data Engineering Monitoring Agent

**Cloud-hosted MVP / Portfolio Project**

An end-to-end cloud-ready application that simulates a robust data engineering monitoring pipeline. It ingests data, runs ETL, performs deterministic data-quality checks, detects anomalies, and uses an OpenAI-powered monitoring agent to interpret failures and generate incident reports.

## Architecture

                    Kaggle Dataset
                         |
                         v
                    Supabase Storage
                         |
                         v
                  Python ETL Pipeline
                         |
              +----------+----------+
              |                     |
              v                     v
        PostgreSQL/Supabase    Pipeline Logs
              |
              v
      Data Quality Engine
              |
              v
      Anomaly Detection
              |
              v
       AI Monitoring Agent
              |
              v
          OpenAI API
              |
              v
       Incident Report
              |
              v
       Streamlit Dashboard

## Prerequisites

- Python 3.11+
- Supabase Account (for PostgreSQL & Storage)
- OpenAI API Key
- Docker (optional, for local DB)

## Setup Commands

### 1. Clone & Install
```bash
git clone https://github.com/yourusername/ai-data-engineering-monitor.git
cd ai-data-engineering-monitor
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Supabase Setup (Database & Storage)
1. Log into [Supabase](https://supabase.com/).
2. Create a new project. Note your database password.
3. Go to **Storage** and create a new public bucket named `data-monitor`.
4. Go to **Project Settings** -> **Database** to get your connection string (`DATABASE_URL`).
5. Go to **Project Settings** -> **API** to get your `SUPABASE_URL` and `SUPABASE_KEY` (anon public).
6. Connect to your database using `psql` or pgAdmin, and run the schema file:
   ```bash
   psql "postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres" -f sql/schema.sql
   ```
   *Alternatively, you can paste the contents of `sql/schema.sql` into the Supabase SQL Editor and hit Run.*

### 4. OpenAI Setup
1. Go to [OpenAI Platform](https://platform.openai.com/api-keys).
2. Generate a new secret key.

### 5. Environment Configuration
Copy the template and fill in your details:
```bash
cp .env.example .env
```
Edit `.env` with your Supabase `SUPABASE_URL`, `SUPABASE_KEY`, `DATABASE_URL`, and `OPENAI_API_KEY`.

### 6. Dataset Download
1. Download the [Telco Customer Churn Dataset](https://www.kaggle.com/datasets/blastchar/telco-customer-churn) from Kaggle.
2. Extract and place `WA_Fn-UseC_-Telco-Customer-Churn.csv` into `data/raw/`.

---

## Demo Instructions

### Run the Pipeline Locally (CLI)
```bash
# Run a clean pipeline execution
python run_pipeline.py

# Simulate a failure (e.g., row drops) and run
python simulate_failure.py --type row_loss
python run_pipeline.py --file data/raw/corrupted_row_loss.csv
```

### Run the Streamlit Dashboard
```bash
streamlit run app.py
```
This opens a local web dashboard where you can view pipeline metrics, data quality results, anomalies, and AI incident reports. You can also simulate failures directly from the UI.

### Testing Commands
Run unit tests with pytest:
```bash
pytest tests/
```

---

## Streamlit Cloud Deployment

1. Push this repository to GitHub (ensure `.env` and `data/raw/*.csv` are ignored).
2. Go to [Streamlit Community Cloud](https://share.streamlit.io/).
3. Click **New app** and select your repository and `app.py`.
4. Before clicking Deploy, click **Advanced settings...**
5. Under **Secrets**, paste the contents of your `.env` file (key-value pairs).
6. Click **Deploy!**

---

## Scalability & Production Evolution

This project is an MVP meant to demonstrate core Data Engineering and AI concepts without unnecessary complexity. In a true enterprise environment, this architecture would evolve:

**Current MVP -> Enterprise Production**
* **Pandas** -> **Apache Spark** (when data size exceeds memory, typically > 10GB or complex distributed joins are needed).
* **Cron/CLI** -> **Apache Airflow** (for complex DAG scheduling, retries, and dependency management).
* **Local CSV** -> **S3 Data Lake + Snowflake/Redshift** (separating compute from massive cloud storage).
* **Custom Quality Engine** -> **Great Expectations or dbt tests** (standardised testing frameworks).
* **Streamlit** -> **Grafana / Datadog / Looker** (enterprise observability and BI).
* **OpenAI API** -> **Private LLM deployment / VPC-bound APIs** (for strict PII compliance).

---

## Security Considerations

* **Secrets Management**: All credentials are read from environment variables or Streamlit Secrets. `.env` is gitignored.
* **Least Privilege**: AWS IAM users should only have read/write access to the specific S3 bucket, not account-wide access.
* **SQL Injection Prevention**: The application exclusively uses SQLAlchemy parameterised queries (e.g., `execute(text("..."), params)`).
* **PII & Data Privacy**: The raw data (simulated customer data) is processed in-memory and loaded to a secure database. In production, PII columns should be hashed/masked before being sent to logs or LLMs. The current prompt to the LLM sends only aggregated *metadata* (row counts, column names with high NULL rates), NOT raw row-level customer data.

---

## Troubleshooting

* **`FileNotFoundError: Dataset not found`**: Ensure you downloaded the Kaggle CSV into `data/raw/`.
* **Database Connection Issues**: Verify your `DATABASE_URL` in `.env`. If using local Docker (`docker compose up -d`), ensure the container is healthy.
* **OpenAI API Errors**: Verify your API key and check if you have available credits. The app will gracefully fall back to a deterministic report if the API fails.
