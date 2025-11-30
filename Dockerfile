# syntax=docker/dockerfile:1.6

ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_HOME=/opt/poetry \
    APP_HOME=/app

WORKDIR ${APP_HOME}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . ${APP_HOME}

RUN mkdir -p data/sessions reference

EXPOSE 8080

CMD ["sh", "-c", "uvicorn fastapi_app.main:app --host 0.0.0.0 --port ${FASTAPI_PORT:-8080} --workers ${UVICORN_WORKERS:-2}"]
