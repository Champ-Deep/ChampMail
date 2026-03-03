# ChampMail Backend Dockerfile
# FastAPI application with Python 3.11

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Cache buster: Railway sets RAILWAY_GIT_COMMIT_SHA per deploy,
# ensuring COPY . . is never stale from a previous build
ARG RAILWAY_GIT_COMMIT_SHA
# Copy application code
COPY . .

# Lint: fail build if any .py file has syntax errors (catches 3.12-only features on 3.11)
RUN python -m compileall -q app/ scripts/

# Create uploads directory for CSV files
RUN mkdir -p /app/uploads/prospect_lists

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Railway assigns PORT dynamically; default to 8000 for local Docker
ENV PORT=8000
EXPOSE ${PORT}

# Health check (uses PORT for flexibility)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health/live || exit 1

# Run migrations then start the application
# Uses migrate.py for migration drift, start.py for visible import errors
CMD sh -c "python scripts/migrate.py && python scripts/start.py"
