FROM python:3.11-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# copy requirements into the image root so build steps reference a stable path
COPY backend/requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel
RUN pip wheel -r /app/requirements.txt -w /wheels

FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
  && rm -rf /var/lib/apt/lists/*

# bring in prebuilt wheels and requirements
COPY --from=builder /wheels /wheels
COPY backend/requirements.txt /app/requirements.txt

# install from local wheels (no network) for deterministic builds
RUN python -m pip install --no-index --find-links=/wheels -r /app/requirements.txt

# copy application code
COPY backend/app /app/app

# copy alembic migrations and docker-specific config
COPY backend/alembic /app/alembic
COPY backend/alembic.docker.ini /app/alembic.ini

# copy and configure entrypoint
COPY backend/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Health check (P6.7) — allows Docker / orchestrators to detect and restart
# the container when the API stops responding.  Uses curl against the
# unversioned /health endpoint which is always available.
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
