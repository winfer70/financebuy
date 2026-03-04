## tickerTap Backend API

This document describes the current tickerTap backend API. All authenticated
endpoints use bearer tokens returned from `POST /auth/login`:

```http
Authorization: Bearer <access_token>
```

Unless otherwise noted, responses are JSON. All endpoints are mounted under
the `/api/v1/` prefix (e.g. `/api/v1/auth/login`).

---

## Table of Contents

1. [Health](#1-health)
2. [Authentication](#2-authentication)
3. [Accounts](#3-accounts)
4. [Transactions](#4-transactions)
5. [Portfolio](#5-portfolio)
6. [Holdings](#6-holdings)
7. [Orders & Trading](#7-orders--trading)
8. [Market Data](#8-market-data)
9. [Portfolio Manager](#9-portfolio-manager)
10. [Chart Templates](#10-chart-templates)
11. [News](#11-news)
12. [Audit Logging](#12-audit-logging)
13. [Admin & Operations](#13-admin--operations)

---

## 1. Health

### GET `/health`

Simple liveness check.

**Response**

```json
{ "status": "ok" }
```

### GET `/docker-compose`

Lightweight endpoint used by tests/CI to confirm the containerised stack is
reachable.

**Response**

```json
{ "status": "ok" }
```

---

## 2. Authentication

Rate limits: `register` — 3/min per IP, `login` — 5/min per IP.

### 2.1 Register — POST `/auth/register`

Create a new user account.

**Request**

```json
{
  "email": "alice@example.com",
  "password": "VeryStrongP@ssw0rd",
  "first_name": "Alice",
  "last_name": "Investor",
  "phone": "+15551234567"
}
```

**201 Created**

```json
{
  "user_id": "0b6a3f8c-4a2f-4a3c-9d1d-8ad4e6a3e1b0",
  "email": "alice@example.com",
  "first_name": "Alice",
  "last_name": "Investor",
  "phone": "+15551234567",
  "kyc_status": "pending",
  "is_active": true
}
```

**Errors**

- 400: `user with this email already exists`

---

### 2.2 Login — POST `/auth/login`

Authenticate a user and obtain an access token. A refresh token is also set
as an httpOnly cookie.

**Request**

```json
{
  "email": "alice@example.com",
  "password": "VeryStrongP@ssw0rd"
}
```

**200 OK**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": "0b6a3f8c-4a2f-4a3c-9d1d-8ad4e6a3e1b0",
  "email": "alice@example.com",
  "first_name": "Alice",
  "last_name": "Investor"
}
```

**Errors**

- 401: `invalid credentials`

---

### 2.3 Refresh token — POST `/auth/refresh`

Rotate the refresh token (read from the httpOnly cookie) and issue a new
access token. The old refresh token is invalidated.

**Request**

No body required. The refresh token is read from the `refresh_token` cookie.

**200 OK**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Errors**

- 401: `missing refresh token` / `invalid or expired refresh token`

---

### 2.4 Logout — POST `/auth/logout`

Invalidate the current refresh token and clear the cookie. Requires
authentication.

**200 OK**

```json
{ "detail": "logged out" }
```

---

### 2.5 Forgot password — POST `/auth/forgot-password`

Request a password reset email. Always returns 200 regardless of whether the
email exists (to prevent enumeration).

**Request**

```json
{
  "email": "alice@example.com"
}
```

**200 OK**

```json
{ "detail": "if an account with that email exists, a reset link has been sent" }
```

---

### 2.6 Reset password — POST `/auth/reset-password`

Set a new password using a reset token received via email.

**Request**

```json
{
  "token": "abc123...",
  "new_password": "NewStrongP@ssw0rd"
}
```

**200 OK**

```json
{ "detail": "password has been reset" }
```

**Errors**

- 400: `invalid or expired token`

---

## 3. Accounts

All accounts endpoints require authentication.

### POST `/accounts`

Create a new investment account for the current user.

**Request**

```json
{
  "account_type": "individual",
  "currency": "USD"
}
```

**201 Created**

```json
{
  "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
  "account_type": "individual",
  "account_number": "a19f47c82b3c",
  "balance": "0.00",
  "currency": "USD",
  "status": "active"
}
```

---

### GET `/accounts/me`

List all accounts owned by the current user.

**200 OK**

```json
[
  {
    "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
    "account_type": "individual",
    "account_number": "a19f47c82b3c",
    "balance": "1500.25",
    "currency": "USD",
    "status": "active"
  }
]
```

---

## 4. Transactions

### POST `/transactions/create`

Create a cash transaction (deposit or withdrawal) on an account owned by the
current user. Balance changes are performed atomically with the transaction
record insert.

**Request**

```json
{
  "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
  "transaction_type": "deposit",
  "amount": "250.75",
  "currency": "USD",
  "description": "Initial funding",
  "reference_number": "DEP-20260223-0001"
}
```

**200 OK**

```json
{
  "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
  "transaction_type": "deposit",
  "amount": "250.75",
  "currency": "USD",
  "description": "Initial funding",
  "reference_number": "DEP-20260223-0001",
  "transaction_id": "e9c2e395-2ea9-4e5c-9c06-70c6a0f04ad7",
  "status": "completed",
  "created_at": "2026-02-23T10:15:32.123456+00:00"
}
```

**Errors**

- 400: `amount must be positive`
- 400: `insufficient funds` (for withdrawals)
- 400: `unsupported transaction_type`
- 404: `account not found`

---

## 5. Portfolio

All portfolio endpoints require authentication.

### GET `/portfolio/positions`

Return per-holding positions (joined `holdings` + `securities`) for all accounts
owned by the current user.

**200 OK**

```json
[
  {
    "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
    "security_id": "f1f3c0b9-2b03-4f5b-8c2a-b6afc2e2f311",
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "quantity": "10.000000",
    "average_cost": "150.00",
    "current_price": "170.25",
    "market_value": "1702.50",
    "currency": "USD"
  }
]
```

---

### GET `/portfolio/summary`

Return per-account and total portfolio summaries (cash + positions value).

**200 OK (with one account)**

```json
{
  "accounts": [
    {
      "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
      "account_type": "individual",
      "currency": "USD",
      "cash_balance": "1500.25",
      "positions_value": "1702.50",
      "total_value": "3202.75"
    }
  ],
  "total_portfolio_value": "3202.75",
  "currency": "USD"
}
```

**200 OK (no accounts)**

```json
{
  "accounts": [],
  "total_portfolio_value": "0.00",
  "currency": "USD"
}
```

---

## 6. Holdings

All holdings endpoints require authentication.

### GET `/holdings`

List raw holdings for a specific account with pagination support.

**Query Parameters**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `account_id` | UUID | Yes | — | Account to list holdings for |
| `limit` | int | No | 50 | Number of records (1–100) |
| `offset` | int | No | 0 | Pagination offset |

**Request**

```http
GET /holdings?account_id=c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c&limit=20&offset=0
```

**200 OK**

```json
[
  {
    "holding_id": "a7e2f1b3-4c5d-6e7f-8a9b-0c1d2e3f4a5b",
    "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
    "security_id": "f1f3c0b9-2b03-4f5b-8c2a-b6afc2e2f311",
    "quantity": "10.000000",
    "average_cost": "150.00",
    "current_price": "170.25"
  }
]
```

---

## 7. Orders & Trading

All orders endpoints require authentication and operate only on accounts owned
by the current user.

### 7.1 Place order — POST `/orders`

Create a new order.

- `"market"` orders are executed immediately and update cash/holdings.
- `"limit"` orders are created with status `"pending"` and do **not** reserve
  cash or holdings; they must be executed later via
  `POST /orders/{order_id}/execute`.

**Request**

```json
{
  "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
  "security_id": "f1f3c0b9-2b03-4f5b-8c2a-b6afc2e2f311",
  "order_type": "market",
  "side": "buy",
  "quantity": "10.000000",
  "price": "170.25"
}
```

**201 Created (market order, filled immediately)**

```json
{
  "order_id": "3b8f8c4f-2a0f-4b5c-b7a9-6e3c2d9e1f10",
  "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
  "security_id": "f1f3c0b9-2b03-4f5b-8c2a-b6afc2e2f311",
  "order_type": "market",
  "side": "buy",
  "quantity": "10.000000",
  "price": "170.25",
  "status": "filled",
  "filled_quantity": "10.000000",
  "filled_price": "170.25"
}
```

**201 Created (limit order, pending)**

```json
{
  "order_id": "94a9c7e1-0d7f-4b64-ae4a-aba2d87e8c42",
  "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
  "security_id": "f1f3c0b9-2b03-4f5b-8c2a-b6afc2e2f311",
  "order_type": "limit",
  "side": "sell",
  "quantity": "5.000000",
  "price": "180.00",
  "status": "pending",
  "filled_quantity": "0.000000",
  "filled_price": null
}
```

**Errors**

- 400: `quantity must be positive`
- 400: `price must be positive`
- 400: `side must be 'buy' or 'sell'`
- 400: `order_type must be 'market' or 'limit'`
- 400: `insufficient funds` (market buy)
- 400: `no position to sell` / `insufficient quantity` (market sell)
- 404: `account not found`

---

### 7.2 Cancel order — POST `/orders/{order_id}/cancel`

Cancel a pending order. Only `"pending"` orders owned by the current user can
be cancelled.

**Request**

```http
POST /orders/94a9c7e1-0d7f-4b64-ae4a-aba2d87e8c42/cancel
```

**200 OK**

```json
{
  "order_id": "94a9c7e1-0d7f-4b64-ae4a-aba2d87e8c42",
  "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
  "security_id": "f1f3c0b9-2b03-4f5b-8c2a-b6afc2e2f311",
  "order_type": "limit",
  "side": "sell",
  "quantity": "5.000000",
  "price": "180.00",
  "status": "cancelled",
  "filled_quantity": "0.000000",
  "filled_price": null
}
```

**Errors**

- 404: `order not found`
- 400: `only pending orders can be cancelled`

---

### 7.3 Execute order — POST `/orders/{order_id}/execute`

Execute a pending limit order. This is a simple placeholder for a real matching
engine:

- Re-checks cash/position constraints at execution time.
- Applies the same buy/sell logic as a market order using the stored
  `quantity` and `price`.

**Request**

```http
POST /orders/94a9c7e1-0d7f-4b64-ae4a-aba2d87e8c42/execute
```

**200 OK**

```json
{
  "order_id": "94a9c7e1-0d7f-4b64-ae4a-aba2d87e8c42",
  "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
  "security_id": "f1f3c0b9-2b03-4f5b-8c2a-b6afc2e2f311",
  "order_type": "limit",
  "side": "sell",
  "quantity": "5.000000",
  "price": "180.00",
  "status": "filled",
  "filled_quantity": "5.000000",
  "filled_price": "180.00"
}
```

**Errors**

- 404: `order not found`
- 400: `only pending orders can be executed`
- 400: `insufficient funds for execution` (buy)
- 400: `no position to sell` / `insufficient quantity for execution` (sell)

---

### 7.4 List orders — GET `/orders`

List orders for the current user. Optionally filter by `account_id` query
parameter.

**Request**

```http
GET /orders
```

or

```http
GET /orders?account_id=c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c
```

**200 OK**

```json
[
  {
    "order_id": "3b8f8c4f-2a0f-4b5c-b7a9-6e3c2d9e1f10",
    "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
    "security_id": "f1f3c0b9-2b03-4f5b-8c2a-b6afc2e2f311",
    "order_type": "market",
    "side": "buy",
    "quantity": "10.000000",
    "price": "170.25",
    "status": "filled",
    "filled_quantity": "10.000000",
    "filled_price": "170.25"
  }
]
```

---

## 8. Market Data

All market data endpoints require authentication. Data is sourced from
yfinance. NaN/Inf values from the data provider are sanitized to `0.0`
before serialization.

### 8.1 Quote — GET `/market/quote/{symbol}`

Retrieve a real-time quote for a single symbol.

**Request**

```http
GET /market/quote/AAPL
```

**200 OK**

```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "price": 170.25,
  "open": 169.50,
  "high": 171.00,
  "low": 168.75,
  "prev_close": 169.00,
  "volume": 52341200,
  "change": 1.25,
  "change_pct": 0.74
}
```

**Errors**

- 404: `symbol not found`

---

### 8.2 OHLCV (yearly) — GET `/market/ohlcv/{symbol}`

Retrieve daily OHLCV bars for a symbol over a given number of years.

**Query Parameters**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| `years` | int | No | 5 | 1–10 |

**Request**

```http
GET /market/ohlcv/AAPL?years=2
```

**200 OK**

```json
{
  "bars": [
    {
      "date": "2024-03-04",
      "open": 169.50,
      "high": 171.00,
      "low": 168.75,
      "close": 170.25,
      "volume": 52341200,
      "is_earnings": false
    }
  ],
  "volume_source": null,
  "interval": "1d",
  "warning": null
}
```

---

### 8.3 OHLCV (interval) — GET `/market/ohlcv_interval/{symbol}`

Retrieve OHLCV bars at a specific interval granularity.

**Query Parameters**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| `interval` | string | No | `"1d"` | yfinance interval strings (`1m`, `5m`, `15m`, `1h`, `1d`, `1wk`, `1mo`) |
| `days` | int | No | 365 | 1–3650 |

**Request**

```http
GET /market/ohlcv_interval/AAPL?interval=1h&days=30
```

**200 OK**

Same response shape as section 8.2.

---

### 8.4 Symbol list — GET `/market/symbols`

Return a list of known securities from the database (id, symbol, name, type).

**200 OK**

```json
[
  {
    "security_id": "f1f3c0b9-2b03-4f5b-8c2a-b6afc2e2f311",
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "security_type": "stock"
  }
]
```

---

### 8.5 Search — GET `/market/search`

Search for securities by ticker or name prefix.

**Query Parameters**

| Parameter | Type | Required | Constraints |
|-----------|------|----------|-------------|
| `q` | string | Yes | min length 1 |

**Request**

```http
GET /market/search?q=AAP
```

**200 OK**

```json
[
  {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "exchange": "NMS",
    "type": "stock"
  }
]
```

---

### 8.6 Bulk quotes — GET `/market/bulk_quotes`

Retrieve quotes for multiple symbols in a single request.

**Query Parameters**

| Parameter | Type | Required | Constraints |
|-----------|------|----------|-------------|
| `symbols` | string | Yes | Comma-separated tickers, max 50 |

**Request**

```http
GET /market/bulk_quotes?symbols=AAPL,MSFT,GOOGL
```

**200 OK**

Array of quote objects (same shape as section 8.1). Symbols that fail to
resolve are omitted from the response.

---

### 8.7 Price change — GET `/market/price_change`

Calculate the price change for a symbol over a given period.

**Query Parameters**

| Parameter | Type | Required | Values |
|-----------|------|----------|--------|
| `symbol` | string | Yes | Ticker symbol |
| `period` | string | Yes | `1D`, `1W`, `1M`, `3M`, `1Y` |

**Request**

```http
GET /market/price_change?symbol=AAPL&period=1M
```

**200 OK**

```json
{
  "symbol": "AAPL",
  "period": "1M",
  "first_close": 165.00,
  "last_close": 170.25,
  "change_pct": 3.18
}
```

---

### 8.8 Bulk SMA — GET `/market/bulk_sma`

Calculate the simple moving average (SMA) for multiple symbols.

**Query Parameters**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| `symbols` | string | Yes | — | Comma-separated tickers, max 50 |
| `period` | int | No | 50 | 5–200 |

**Request**

```http
GET /market/bulk_sma?symbols=AAPL,MSFT&period=50
```

**200 OK**

```json
[
  { "symbol": "AAPL", "sma": 168.42 },
  { "symbol": "MSFT", "sma": 412.15 }
]
```

---

## 9. Portfolio Manager

All portfolio manager endpoints require authentication. Custom portfolios are
independent of trading accounts and used for tracking external holdings.

Route prefix: `/portfolio-manager`

### 9.1 List portfolios — GET `/portfolio-manager/portfolios`

Return all portfolios owned by the current user.

**200 OK**

```json
[
  {
    "portfolio_id": "d1e2f3a4-b5c6-7d8e-9f0a-1b2c3d4e5f6a",
    "name": "Tech Holdings",
    "strategy": "Long-term growth in semiconductor and AI sectors",
    "created_at": "2026-02-20T14:30:00+00:00"
  }
]
```

---

### 9.2 Create portfolio — POST `/portfolio-manager/portfolios`

Create a new custom portfolio.

**Request**

```json
{
  "name": "Tech Holdings",
  "strategy": "Long-term growth in semiconductor and AI sectors"
}
```

**201 Created**

```json
{
  "portfolio_id": "d1e2f3a4-b5c6-7d8e-9f0a-1b2c3d4e5f6a",
  "name": "Tech Holdings",
  "strategy": "Long-term growth in semiconductor and AI sectors",
  "created_at": "2026-02-20T14:30:00+00:00"
}
```

**Errors**

- 400: validation errors (name required, 1–128 chars)

---

### 9.3 Delete portfolio — DELETE `/portfolio-manager/portfolios/{portfolio_id}`

Delete a portfolio and all its positions (cascade).

**204 No Content**

**Errors**

- 404: `portfolio not found`

---

### 9.4 List positions — GET `/portfolio-manager/portfolios/{portfolio_id}/positions`

Return all positions in a portfolio.

**200 OK**

```json
[
  {
    "position_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "portfolio_id": "d1e2f3a4-b5c6-7d8e-9f0a-1b2c3d4e5f6a",
    "ticker": "NVDA",
    "name": "NVIDIA Corporation",
    "quantity": "25.000000",
    "purchase_date": "2025-06-15T00:00:00+00:00",
    "purchase_price": "450.00",
    "group_tag": "semiconductors",
    "is_excluded": false,
    "asset_type": "stock",
    "physical_type": null,
    "stop_loss": "400.00",
    "created_at": "2026-02-20T14:35:00+00:00"
  }
]
```

---

### 9.5 Add position — POST `/portfolio-manager/portfolios/{portfolio_id}/positions`

Add a single position to a portfolio.

**Request**

```json
{
  "ticker": "NVDA",
  "name": "NVIDIA Corporation",
  "quantity": "25.000000",
  "purchase_date": "2025-06-15T00:00:00Z",
  "purchase_price": "450.00",
  "group_tag": "semiconductors",
  "asset_type": "stock",
  "stop_loss": "400.00"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `ticker` | string | Yes | — | Ticker symbol (1–20 chars) |
| `name` | string | No | — | Display name (max 256 chars) |
| `quantity` | decimal | Yes | — | Number of shares (> 0) |
| `purchase_date` | datetime | No | — | Date of purchase |
| `purchase_price` | decimal | Yes | — | Price per share (> 0) |
| `group_tag` | string | No | — | Grouping label (max 64 chars) |
| `asset_type` | string | No | `"stock"` | `stock`, `etf`, `crypto`, `commodity`, `futures` |
| `physical_type` | string | No | — | Physical commodity type (max 20 chars) |
| `stop_loss` | decimal | No | — | Stop-loss price (> 0) |

**201 Created**

Same shape as the position object in section 9.4.

---

### 9.6 Bulk import — POST `/portfolio-manager/portfolios/{portfolio_id}/import`

Import multiple positions at once (used by the CSV import feature).

**Request**

Array of position objects (same fields as section 9.5).

```json
[
  { "ticker": "NVDA", "quantity": "25", "purchase_price": "450.00" },
  { "ticker": "AMD", "quantity": "50", "purchase_price": "120.00" }
]
```

**201 Created**

Array of created position objects.

---

### 9.7 Update position — PATCH `/portfolio-manager/positions/{position_id}`

Partially update an existing position. All fields are optional.

**Request**

```json
{
  "quantity": "30.000000",
  "stop_loss": "420.00"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `quantity` | decimal | New quantity (> 0) |
| `purchase_price` | decimal | New purchase price (> 0) |
| `group_tag` | string | New group label (max 64 chars) |
| `is_excluded` | bool | Exclude from heatmap/portfolio calculations |
| `stop_loss` | decimal | New stop-loss price (> 0) |

**200 OK**

Updated position object.

**Errors**

- 404: `position not found`

---

### 9.8 Delete position — DELETE `/portfolio-manager/positions/{position_id}`

Remove a position from its portfolio.

**204 No Content**

**Errors**

- 404: `position not found`

---

### 9.9 Sell position — POST `/portfolio-manager/positions/{position_id}/sell`

Reduce a position's quantity. If the sell quantity equals the position quantity,
the position is deleted entirely.

**Request**

```json
{
  "quantity": "10.000000"
}
```

**200 OK**

Updated position object with reduced quantity, or `null` if the position was
fully sold and deleted.

**Errors**

- 400: `sell quantity exceeds position quantity`
- 404: `position not found`

---

## 10. Chart Templates

All chart template endpoints require authentication. Templates store saved
chart configurations (drawings, overlays) that persist across sessions.

Route prefix: `/chart-templates`

### 10.1 List templates — GET `/chart-templates`

Return all chart templates owned by the current user.

**200 OK**

```json
[
  {
    "template_id": "b1c2d3e4-f5a6-7b8c-9d0e-1f2a3b4c5d6e",
    "name": "AAPL Daily Setup",
    "symbol": "AAPL",
    "interval": "1d",
    "drawings_json": [
      { "type": "trendline", "points": [[0, 150], [100, 170]] }
    ],
    "overlays_json": {
      "ema": { "period": 20, "visible": true },
      "sma": { "period": 50, "visible": true }
    },
    "created_at": "2026-03-01T10:00:00+00:00",
    "updated_at": "2026-03-02T15:30:00+00:00"
  }
]
```

---

### 10.2 Create template — POST `/chart-templates`

Save a new chart template.

**Request**

```json
{
  "name": "AAPL Daily Setup",
  "symbol": "AAPL",
  "interval": "1d",
  "drawings_json": [
    { "type": "trendline", "points": [[0, 150], [100, 170]] }
  ],
  "overlays_json": {
    "ema": { "period": 20, "visible": true }
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Template name (1–128 chars) |
| `symbol` | string | No | Scoped to this symbol (max 20 chars) |
| `interval` | string | No | Scoped to this interval (max 10 chars) |
| `drawings_json` | array | No | Drawing tool data (default `[]`) |
| `overlays_json` | object | No | Overlay/indicator configuration |

**201 Created**

Created template object (same shape as section 10.1).

---

### 10.3 Get template — GET `/chart-templates/{template_id}`

Retrieve a single chart template by ID.

**200 OK**

Template object (same shape as section 10.1).

**Errors**

- 404: `template not found`

---

### 10.4 Update template — PATCH `/chart-templates/{template_id}`

Partially update an existing chart template. All fields are optional.

**Request**

```json
{
  "drawings_json": [
    { "type": "rectangle", "bounds": [150, 170, 200, 180] }
  ]
}
```

**200 OK**

Updated template object.

**Errors**

- 404: `template not found`

---

### 10.5 Delete template — DELETE `/chart-templates/{template_id}`

Delete a saved chart template.

**204 No Content**

**Errors**

- 404: `template not found`

---

## 11. News

All news endpoints require authentication. Articles are fetched from four
sources (Yahoo Finance RSS, Google News RSS, Finviz HTML scraping, MarketWatch
RSS), classified by FinBERT sentiment, and annotated with portfolio flags.
Results are cached in memory with a 5-minute TTL.

Route prefix: `/news`

### 11.1 Aggregated feed — GET `/news/feed`

Return a news feed for the authenticated user's portfolio tickers. Articles
from all four sources are deduplicated by URL, classified by FinBERT, and
sorted by publication date descending. Articles mentioning holdings are
flagged with `in_portfolio: true`.

**200 OK**

```json
[
  {
    "title": "NVIDIA Reports Record Q4 Revenue",
    "url": "https://finance.yahoo.com/news/nvidia-q4-2026...",
    "source": "yahoo",
    "published_at": "2026-03-04T09:15:00+00:00",
    "tickers": ["NVDA"],
    "in_portfolio": true,
    "sentiment": "positive",
    "sentiment_score": 0.92,
    "summary": "NVIDIA reported record quarterly revenue of $38.1B..."
  },
  {
    "title": "Fed Holds Rates Steady",
    "url": "https://www.marketwatch.com/story/fed-rates...",
    "source": "marketwatch",
    "published_at": "2026-03-04T08:00:00+00:00",
    "tickers": [],
    "in_portfolio": false,
    "sentiment": "neutral",
    "sentiment_score": 0.65,
    "summary": "The Federal Reserve held interest rates unchanged..."
  }
]
```

---

### 11.2 Ticker news — GET `/news/tickers/{ticker}`

On-demand deep fetch of news for a single ticker. Bypasses the top-10 ticker
limit used in the aggregated feed and queries all sources for the specified
symbol.

**Request**

```http
GET /news/tickers/AAPL
```

**200 OK**

Array of article objects (same shape as section 11.1).

**Errors**

- 400: `Ticker symbol is required.`

---

## 12. Audit Logging

The backend writes immutable audit records to the `audit_log` table for key
security- and finance-sensitive actions. Each record captures:

- `user_id`: the acting user (where applicable),
- `action`: a short verb describing the event,
- `table_name` and `record_id`: the primary record that was affected,
- `old_values` / `new_values`: structured snapshots of important fields,
- `ip_address`: the raw client IP as seen by the API layer,
- `user_agent`: the HTTP `User-Agent` header.

Actions that emit audit entries:

- Successful user registration (`user_register`)
- Successful login (`login_success`)
- Successful account creation (`account_create`)
- Successful cash transactions (`transaction_create`) that update balances
- User lock/unlock by admin (`user_lock` / `user_unlock`)
- Account lock/unlock by admin (`account_lock` / `account_unlock`)

---

## 13. Admin & Operations

Admin endpoints are intended for operational tooling and require an **admin
user**. Admins are defined via the `ADMIN_EMAILS` environment variable:

```bash
export ADMIN_EMAILS="alice@example.com,bob@example.com"
```

Any authenticated user whose email matches this comma-separated list gains
access to the `/admin` routes.

All admin endpoints require:

```http
Authorization: Bearer <access_token_for_admin_user>
```

### 13.1 List users — GET `/admin/users`

Return all users in the system, ordered by `created_at` descending.

**Request**

```http
GET /admin/users
```

**200 OK**

```json
[
  {
    "user_id": "0b6a3f8c-4a2f-4a3c-9d1d-8ad4e6a3e1b0",
    "email": "alice@example.com",
    "first_name": "Alice",
    "last_name": "Investor",
    "phone": "+15551234567",
    "kyc_status": "pending",
    "is_active": true
  }
]
```

**Errors**

- 403: `admin privileges required` (for non-admin users).

---

### 13.2 Lock / unlock users

Locking a user sets `is_active = false`; unlocking sets `is_active = true`.
Both actions emit `user_lock` / `user_unlock` audit log entries.

#### POST `/admin/users/{user_id}/lock`

**Request**

```http
POST /admin/users/0b6a3f8c-4a2f-4a3c-9d1d-8ad4e6a3e1b0/lock
```

**200 OK**

```json
{
  "user_id": "0b6a3f8c-4a2f-4a3c-9d1d-8ad4e6a3e1b0",
  "email": "alice@example.com",
  "first_name": "Alice",
  "last_name": "Investor",
  "phone": "+15551234567",
  "kyc_status": "pending",
  "is_active": false
}
```

#### POST `/admin/users/{user_id}/unlock`

**Request**

```http
POST /admin/users/0b6a3f8c-4a2f-4a3c-9d1d-8ad4e6a3e1b0/unlock
```

**200 OK**

```json
{
  "user_id": "0b6a3f8c-4a2f-4a3c-9d1d-8ad4e6a3e1b0",
  "email": "alice@example.com",
  "first_name": "Alice",
  "last_name": "Investor",
  "phone": "+15551234567",
  "kyc_status": "pending",
  "is_active": true
}
```

**Errors (both endpoints)**

- 404: `user not found`
- 403: `admin privileges required`

---

### 13.3 Lock / unlock accounts

Locking an account sets `status = "locked"`; unlocking sets `status = "active"`.
Both actions emit `account_lock` / `account_unlock` audit entries.

#### POST `/admin/accounts/{account_id}/lock`

**Request**

```http
POST /admin/accounts/c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c/lock
```

**200 OK**

```json
{
  "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
  "account_type": "individual",
  "account_number": "a19f47c82b3c",
  "balance": "1500.25",
  "currency": "USD",
  "status": "locked"
}
```

#### POST `/admin/accounts/{account_id}/unlock`

**Request**

```http
POST /admin/accounts/c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c/unlock
```

**200 OK**

```json
{
  "account_id": "c5f58f1f-1e96-4cf0-8f21-7ad43e9f1f2c",
  "account_type": "individual",
  "account_number": "a19f47c82b3c",
  "balance": "1500.25",
  "currency": "USD",
  "status": "active"
}
```

**Errors (both endpoints)**

- 404: `account not found`
- 403: `admin privileges required`

---

### 13.4 View audit logs — GET `/admin/audit-logs`

List audit log entries, optionally filtered by `user_id` and `action`. Results
are ordered by `created_at` descending and limited by `limit` (default 100,
max 1000).

**Query Parameters**

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `user_id` | UUID | No | — |
| `action` | string | No | — |
| `limit` | int | No | 100 (max 1000) |

**Request**

```http
GET /admin/audit-logs?limit=50&action=transaction_create
```

**200 OK**

```json
[
  {
    "log_id": 123,
    "user_id": "0b6a3f8c-4a2f-4a3c-9d1d-8ad4e6a3e1b0",
    "action": "transaction_create",
    "table_name": "transactions",
    "record_id": "e9c2e395-2ea9-4e5c-9c06-70c6a0f04ad7",
    "old_values": { "balance": "1500.25" },
    "new_values": {
      "balance": "1751.00",
      "transaction_type": "deposit",
      "amount": "250.75",
      "currency": "USD"
    },
    "ip_address": "203.0.113.42",
    "user_agent": "Mozilla/5.0 (...",
    "created_at": "2026-02-23T10:15:32.123456+00:00"
  }
]
```

**Errors**

- 403: `admin privileges required`

---

> **Note:** This file is the canonical reference for the backend API. When new
> endpoints are added or existing ones change, they should be documented here
> with updated examples to keep the implementation and docs in sync.
