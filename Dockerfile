# ==============================================================
# Dockerfile — AI Data Engineering Monitoring Agent
# ==============================================================
# Build:  docker build -t ai-data-monitor .
# Run:    docker run --env-file .env -p 8501:8501 ai-data-monitor
# ==============================================================

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (for psycopg2)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p data/raw data/processed

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8501/_stcore/health')" || exit 1

# Run Streamlit dashboard
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
