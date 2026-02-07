# Docker Deployment Guide

This guide covers deploying the MicroHack AI service using Docker.

## Quick Start

```bash
# 1. Create .env file (see Environment Variables section)
# 2. Start all services
docker-compose up -d

# 3. Check logs
docker-compose logs -f api
```

The API will be available at `http://localhost:8080`.

## Services

The `docker-compose.yml` includes:

| Service    | Port | Description                             |
| ---------- | ---- | --------------------------------------- |
| `api`      | 8080 | FastAPI AI service                      |
| `postgres` | 5432 | PostgreSQL for conversation checkpoints |
| `pgadmin`  | 8890 | Database admin UI (optional)            |

## Environment Variables

Create a `.env` file in the same directory as `docker-compose.yml`:

```env
# ═══════════════════════════════════════════════════════════
# REQUIRED
# ═══════════════════════════════════════════════════════════

# Mistral AI API key for LLM inference
MISTRAL_API_KEY=your_mistral_api_key_here

# Backend API URL (use host.docker.internal if backend runs on host)
API_BASE_URL=http://host.docker.internal:3000

# Admin credentials for backend authentication
ADMIN_EMAIL=admin@apcs-port.dz
ADMIN_PASSWORD=Admin@APCS2026!

# API key that clients must send in X-API-Key header
AGENT_API_KEY=your_secret_api_key_here

# ═══════════════════════════════════════════════════════════
# OPTIONAL — LangSmith Tracing
# ═══════════════════════════════════════════════════════════

LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=microhack_ai
LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
```

### Backend URL Configuration

The AI container needs to reach the backend API:

| Scenario                       | API_BASE_URL                       |
| ------------------------------ | ---------------------------------- |
| Backend on host machine        | `http://host.docker.internal:3000` |
| Backend in same Docker network | `http://backend:3000`              |
| Backend on remote server       | `http://your-server-ip:3000`       |

## Dockerfile

```dockerfile
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

# Ensure Python output is sent straight to Docker logs
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080", "--access-log"]
```

## Docker Compose

```yaml
version: "3.8"

services:
  postgres:
    image: postgres:16-alpine
    container_name: microhack_postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: 123456789
      POSTGRES_DB: microhack_checkpoints
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d microhack_checkpoints"]
      interval: 5s
      timeout: 5s
      retries: 5

  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: microhack_pgadmin
    restart: unless-stopped
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@microhack.com
      PGADMIN_DEFAULT_PASSWORD: admin123
    ports:
      - "8890:80"
    depends_on:
      postgres:
        condition: service_healthy

  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: microhack_api
    restart: unless-stopped
    ports:
      - "8080:8080"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    deploy:
      resources:
        limits:
          cpus: "4"
          memory: 4G
        reservations:
          cpus: "2"
          memory: 2G
    environment:
      CHECKPOINT_DB_URL: postgresql://postgres:123456789@postgres:5432/microhack_checkpoints
      API_BASE_URL: ${API_BASE_URL}
      ADMIN_EMAIL: ${ADMIN_EMAIL:-admin@apcs-port.dz}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:-Admin@APCS2026!}
      MISTRAL_API_KEY: ${MISTRAL_API_KEY}
      LANGSMITH_API_KEY: ${LANGSMITH_API_KEY}
      LANGSMITH_TRACING: ${LANGSMITH_TRACING:-true}
      LANGSMITH_PROJECT: ${LANGSMITH_PROJECT:-microhack_ai}
      LANGSMITH_ENDPOINT: ${LANGSMITH_ENDPOINT:-https://eu.api.smith.langchain.com}
      AGENT_API_KEY: ${AGENT_API_KEY}
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  pgdata:
```

## Commands

### Build and Start

```bash
# Build and start all services
docker-compose up -d --build

# Start only (if already built)
docker-compose up -d
```

### Logs

```bash
# All services
docker-compose logs -f

# API only
docker-compose logs -f api

# Last 100 lines
docker-compose logs --tail=100 api
```

### Stop

```bash
# Stop all services (keeps data)
docker-compose down

# Stop and remove volumes (deletes checkpoint data!)
docker-compose down -v
```

### Restart API

```bash
docker-compose restart api
```

### Rebuild API

```bash
docker-compose up -d --build api
```

## Health Checks

### API Health

```bash
curl http://localhost:8080/docs
```

### PostgreSQL Health

```bash
docker exec microhack_postgres pg_isready -U postgres
```

### Test Chat Endpoint

```bash
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secret_api_key_here" \
  -d '{
    "message": "Hello",
    "user_id": "test",
    "user_role": "CARRIER"
  }'
```

## Production Considerations

### 1. Security

- Change default PostgreSQL password in `docker-compose.yml`
- Use strong `AGENT_API_KEY`
- Consider removing pgAdmin in production
- Use HTTPS reverse proxy (nginx, traefik)

### 2. Resource Limits

The compose file sets resource limits:

- **CPU:** 4 cores max, 2 reserved
- **Memory:** 4GB max, 2GB reserved

Adjust based on your server capacity.

### 3. Persistent Data

Conversation checkpoints are stored in the `pgdata` volume. Back up regularly:

```bash
docker exec microhack_postgres pg_dump -U postgres microhack_checkpoints > backup.sql
```

### 4. Scaling

For high availability, consider:

- Running multiple API containers behind a load balancer
- Using managed PostgreSQL (AWS RDS, Azure, etc.)
- Implementing Redis for rate limiting

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs api

# Common issues:
# - MISTRAL_API_KEY not set
# - Backend not reachable at API_BASE_URL
# - PostgreSQL connection failed
```

### API returns 401

- Check `AGENT_API_KEY` in `.env` matches what client sends
- Check `ADMIN_EMAIL` / `ADMIN_PASSWORD` are correct for backend

### Cannot connect to backend

If backend runs on host machine:

```env
API_BASE_URL=http://host.docker.internal:3000
```

If on Linux and `host.docker.internal` doesn't work:

```bash
# Get host IP
ip route show default | awk '/default/ {print $3}'

# Use that IP in API_BASE_URL
API_BASE_URL=http://172.17.0.1:3000
```

### Database connection issues

```bash
# Check postgres is running
docker ps | grep postgres

# Check network connectivity
docker exec microhack_api ping postgres
```

## pgAdmin Access

1. Open `http://localhost:8890`
2. Login: `admin@microhack.com` / `admin123`
3. Add server:
   - Host: `postgres`
   - Port: `5432`
   - User: `postgres`
   - Password: `123456789`
   - Database: `microhack_checkpoints`
