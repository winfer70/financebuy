from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import accounts, admin, auth_routes, orders, portfolio, transactions

app = FastAPI(title="tickerTap API")

# Minimal CORS - adjust origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/docker-compose")
async def docker_compose():
    # lightweight endpoint used by tests to validate docker-compose setup
    return {"status": "ok"}
