# Gradient API. Not verified in this dev environment (no Docker daemon) — standard build.
FROM python:3.11-slim

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
# Env (SUPABASE_*, AI_*, CORS_ORIGINS) is provided via env_file in docker-compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
