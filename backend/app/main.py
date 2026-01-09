from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import transactions

app = FastAPI(title="FinanceBuy API")

# Minimal CORS - adjust origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transactions.router, prefix="/transactions", tags=["transactions"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/docker-compose")
async def docker_compose():
    # lightweight endpoint used by tests to validate docker-compose setup
    return {"status": "ok"}


@app.get("/docker-compose")
async def docker_compose_health():
    return {"status": "ok"}
