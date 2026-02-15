# Use the official Python slim image for a small, secure footprint
FROM python:3.11-slim

# 1. Standard Enterprise Env Vars
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 2. Install system dependencies for MCP and networking tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 3. Python Dependency Layer
# This leverages Docker caching to speed up builds
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Copy Project Folders (Matching your extra_packages in ADK)
COPY agents/ ./agents/
COPY tools/ ./tools/
COPY memory/ ./memory/
COPY observability/ ./observability/
COPY engine.py .
COPY .env . 

# 5. Local Entrypoint
# For local testing, we run the script that triggers the ADK deployment 
# or a local test script.
CMD ["python", "engine.py"]