## tickerTap Backend API

This document describes the current tickerTap backend API. All authenticated
endpoints use bearer tokens returned from `POST /auth/login`:

```http
Authorization: Bearer <access_token>
```

Unless otherwise noted, responses are JSON.

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

### POST `/auth/register`

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

**400 Bad Request (email exists)**

```json
{ "detail": "user with this email already exists" }
```

---

### POST `/auth/login`

Authenticate a user and obtain an access token.

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
  "token_type": "bearer"
}
```

**401 Unauthorized**

```json
{ "detail": "invalid credentials" }
```

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

## 6. Orders & Trading

All orders endpoints require authentication and operate only on accounts owned
by the current user.

### 6.1 Place order — POST `/orders`

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
  "order_type": "market",  // or "limit"
  "side": "buy",           // or "sell"
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

### 6.2 Cancel order — POST `/orders/{order_id}/cancel`

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

### 6.3 Execute order — POST `/orders/{order_id}/execute`

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

### 6.4 List orders — GET `/orders`

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

> **Note:** This file is the canonical reference for the backend API. When new
> endpoints are added or existing ones change, they should be documented here
> with updated examples to keep the implementation and docs in sync.

---

## 7. Audit logging

The backend writes immutable audit records to the `audit_log` table for key
security- and finance-sensitive actions. Each record captures:

- `user_id`: the acting user (where applicable),
- `action`: a short verb describing the event,
- `table_name` and `record_id`: the primary record that was affected,
- `old_values` / `new_values`: structured snapshots of important fields,
- `ip_address`: the raw client IP as seen by the API layer,
- `user_agent`: the HTTP `User-Agent` header.

As of now, the following actions emit audit entries:

- Successful user registration (`user_register`),
- Successful login (`login_success`),
- Successful account creation (`account_create`),
- Successful cash transactions (`transaction_create`) that update balances.

Future work may extend audit coverage to order placement, execution, and
administrative operations.

---

## 8. Admin & Operations

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

### 8.1 List users — GET `/admin/users`

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

### 8.2 Lock / unlock users

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

### 8.3 Lock / unlock accounts

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

### 8.4 View audit logs — GET `/admin/audit-logs`

List audit log entries, optionally filtered by `user_id` and `action`. Results
are ordered by `created_at` descending and limited by `limit` (default 100,
max 1000).

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

