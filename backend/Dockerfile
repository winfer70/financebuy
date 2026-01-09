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

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
