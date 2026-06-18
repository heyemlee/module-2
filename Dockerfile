FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy project metadata + source, then install (hatchling needs app/ at build time)
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# Runtime data dir for SQLite
RUN mkdir -p /app/data

EXPOSE 8000

# Shell form so ${PORT} (injected by Railway) expands; falls back to 8000 locally.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
