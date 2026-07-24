# Stage 1: build the React frontend (Node only needed at build time)
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the actual runtime image - Python only, no Node
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Replace whatever frontend/dist may have been copied above with the
# real build output from stage 1 (keeps .dockerignore simple either way).
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV AGENTOS_DB=/data/agentos.db \
    AGENTOS_WORKSPACE=/data/workspace
RUN mkdir -p /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
