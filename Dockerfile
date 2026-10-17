# One container = the whole product (web app + API + AI + simulator). Built for Cloud Run.

# 1) Build the React web app
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2) Python service that also serves the built web app
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 ENV=production
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ backend/
COPY database/ database/
COPY data/ data/
COPY models/ models/
COPY --from=web /web/dist frontend/dist
# Re-train if the model files were not committed (takes ~30 s; uses the datasets in data/raw).
RUN test -f models/rul_model.joblib || (cd backend && python -m pipeline.run_all)
RUN useradd --create-home opex && chown -R opex /app
USER opex
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
