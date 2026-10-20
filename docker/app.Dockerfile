# Build the frontend
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# API + worker image (the worker runs the same image with a different command)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/mwg.db \
    FRONTEND_DIST=/app/frontend/dist
WORKDIR /app/backend
COPY backend/ ./
RUN pip install --no-cache-dir -e .
COPY --from=web /web/dist /app/frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "python -m app.cli init-db && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
