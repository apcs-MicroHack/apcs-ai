FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg (PostgreSQL driver)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure Python output is sent straight to Docker logs (no buffering)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose the API port
EXPOSE 8080

# Run the FastAPI server with access logging
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080", "--access-log"]
