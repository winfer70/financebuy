# trading-ml/Dockerfile — Quant ML container for TickerTap.
#
# Provides internal-only FastAPI endpoints for model inference,
# training, and market regime classification.  Not exposed to users;
# called exclusively by the trading worker and backend services.
#
# Build / run via docker-compose (see project root docker-compose.yml).

FROM python:3.11-slim

# System dependencies for numpy/pandas/scikit-learn compilation
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8001"]
