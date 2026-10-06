# Interview Preparation Guide

This document prepares you to explain this project in a data engineering or cloud engineering interview.

## 60-Second Project Explanation
"I built a cloud-hosted data engineering monitoring agent that acts as an automated 'first responder' for data pipelines. It ingests raw CSV data, uploads it to AWS S3, runs an ETL pipeline to clean and load the data into a Supabase PostgreSQL database. As it processes the data, a custom deterministic data-quality engine checks for schema drift, null spikes, and volume drops. If anomalies are detected, the system sends the metadata to an OpenAI agent which acts as an analyst—generating a human-readable incident report with root cause hypotheses and recommended actions. The entire system is viewable through a Streamlit dashboard."

## 2-Minute Architecture Explanation
"The architecture is designed to be modular and cloud-ready. 
1. **Storage**: Raw and processed data is backed up to Supabase Storage. 
2. **Compute (ETL)**: A Python pipeline extracts the data, normalises schemas, cleans anomalies (like empty string charges), and enforces data types. 
3. **Database**: The cleaned data and pipeline telemetry (runs, quality results, anomalies) are loaded into a managed Supabase PostgreSQL database using SQLAlchemy.
4. **Monitoring Engine**: A custom Python module runs deterministic checks—comparing current row counts to historical runs and checking column constraints.
5. **AI Layer**: The OpenAI API is used strictly as an interpretation layer. It takes the deterministic facts (e.g., 'Column X null rate spiked to 40%') and returns a JSON incident report detailing potential business impact.
6. **Presentation**: A Streamlit dashboard queries the PostgreSQL database to visualise pipeline health and AI reports."

## Key Technical Decisions

### Why Data Engineering?
Data engineering is the foundation of AI and Analytics. Without clean, reliable, and accessible data, machine learning models fail. I built this project to demonstrate that I understand the entire lifecycle: ingestion, transformation, storage, and—crucially—observability and quality monitoring.

### Why Supabase Storage instead of AWS S3?
For this portfolio MVP, using Supabase for both the PostgreSQL database and file storage eliminates the need for an AWS account (and credit card requirements). Supabase Storage is built on top of standard cloud primitives but offers a simpler API and is fully free for this scale. In an enterprise scenario, we would definitely use S3, but Supabase acts as a great unified backend here.

### Why PostgreSQL (Supabase)?
PostgreSQL is a robust, ACID-compliant relational database. Supabase provides a managed, cloud-hosted version that is perfect for an MVP, removing infrastructure overhead while still allowing me to write standard SQL, handle foreign keys, and manage indexing for my telemetry tables.

### Why Streamlit?
Streamlit allows data engineers and data scientists to build interactive web applications purely in Python. It's the fastest way to build an internal operational dashboard without having to write React or manage complex frontend state.

### Why Python?
Python is the lingua franca of data engineering. Its ecosystem (Pandas for data manipulation, SQLAlchemy for database ORM, Supabase Python client) allows for rapid development of robust ETL pipelines.

### Why use an LLM?
Standard monitoring alerts (e.g., "Alert: Null rate > 10%") lack context. An LLM acts as a junior analyst, reading the metadata and providing a human-readable summary, hypothesising root causes (e.g., "An upstream schema change may have dropped the total_charges column"), and recommending next steps, saving senior engineers time during triage.

### Why deterministic validation instead of AI validation?
**Crucial Point:** LLMs are non-deterministic and can hallucinate. You should *never* rely on an LLM to count rows, calculate averages, or determine if a pipeline failed. The system uses strict Python logic to determine failures (deterministic facts), and only uses the LLM to *interpret* those facts.

## Scaling & Evolution Questions

### How does anomaly detection work?
It uses configurable thresholds (e.g., `ROW_COUNT_CHANGE_THRESHOLD=20%`). It queries the database for the last successful pipeline run, compares the current row count, and calculates the percentage drift.

### How would you scale it?
I would replace Pandas with Apache Spark to handle distributed processing across a cluster. I would replace the cron/CLI execution with Apache Airflow for dependency management, retries, and scheduling. I would use a Data Warehouse like Snowflake instead of PostgreSQL for the final analytical layer.

### How would you add Airflow?
I would wrap the Python functions (`run_etl`, `run_quality_checks`) into Airflow `PythonOperator` tasks, creating a DAG (Directed Acyclic Graph). This would allow the pipeline to run on a schedule, automatically retry on transient failures, and trigger alerts via Slack on failure.

### How would you add Spark?
I would replace the Pandas ingestion (`pd.read_csv`) with PySpark (`spark.read.csv`). Instead of processing data in memory on a single machine, Spark would distribute the DataFrame across worker nodes, allowing the pipeline to scale to terabytes of data.

### How would you handle millions of rows?
Pandas loads all data into RAM. For millions of rows, I would use chunking (`chunksize` in Pandas/SQLAlchemy) to process the data in batches, or transition to a distributed framework like Spark or Dask.

### How would you handle streaming?
Instead of batch processing CSVs, I would use Apache Kafka or AWS Kinesis to ingest events in real-time. The ETL pipeline would be rewritten using Spark Structured Streaming or Apache Flink to process micro-batches continuously.

### How would you handle schema evolution?
Currently, the pipeline validates against a hardcoded expected schema. In production, I would use a schema registry (like AWS Glue or Confluent Schema Registry) to manage schema versions, and implement rules for backward/forward compatibility (e.g., allowing new columns but failing on removed columns).

### How would you handle pipeline failure / implement retries?
Currently, errors are caught, logged, and marked as 'FAILED' in the database. In production, I would use an orchestrator like Airflow to automatically retry tasks that fail due to transient errors (like network timeouts). For logic errors, I would implement a Dead Letter Queue (DLQ) to store failed rows for manual inspection while allowing good rows to proceed.

### How would you reduce OpenAI costs?
1. Only call the API when anomalies are actually detected (implemented).
2. Send only aggregated metadata, not raw row data (implemented).
3. Use a smaller, cheaper model like `gpt-4o-mini` for basic interpretation (implemented).
4. Cache identical anomaly patterns to avoid redundant API calls.

### What happens when OpenAI is unavailable?
The pipeline must not break. The code wraps the API call in a `try/except` block. If it fails, it generates a deterministic "fallback report" using local Python logic so the dashboard still shows the error to the user.

### What are the limitations of this MVP?
- Uses Pandas, which is bound by single-machine memory limits.
- Lacks a robust scheduler like Airflow.
- Requires full-table replacement (`if_exists="replace"`) instead of incremental upserts, which is inefficient for massive datasets.
