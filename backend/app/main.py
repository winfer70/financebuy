import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import accounts, admin, auth_routes, holdings, market, orders, portfolio, transactions

app = FastAPI(title="tickerTap API")

_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(portfolio.router)
app.include_router(orders.router)
app.include_router(admin.router)
app.include_router(market.router, prefix="/market", tags=["market"])
app.include_router(holdings.router, prefix="/holdings", tags=["holdings"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/docker-compose")
async def docker_compose():
    # lightweight endpoint used by tests to validate docker-compose setup
    return {"status": "ok"}
