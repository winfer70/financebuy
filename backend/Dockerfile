FROM python:3.11-slim AS builder
WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN python -m pip install --upgrade pip
RUN pip wheel -r backend/requirements.txt -w /wheels

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels -r backend/requirements.txt

# Create non-root user
RUN useradd --create-home appuser
USER appuser
COPY backend/app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
