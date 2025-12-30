# TinkerStore Backend API Documentation

This document describes the **current implementation** of the TinkerStore backend API, including request flow, authentication behavior, caching strategy, and error handling.

The backend is built with **FastAPI**, persists data in **Turso (SQLite)** via SQLAlchemy, uses **Redis** for caching, and integrates **Clerk** for authentication and **ImageKit** for media uploads.

---

## Architecture Overview

### Core Technologies

* **Framework**: FastAPI
* **Database**: SQLite (Turso) via SQLAlchemy ORM
* **Caching**: Redis (Redis Cloud)
* **Authentication**: Clerk (JWT verification via middleware decorators)
* **Media/CDN**: ImageKit.io (signed client-side uploads)
* **Config Management**: Pydantic `BaseSettings`

---

## Application Lifecycle

### Startup (`lifespan`)

On application startup:

1. `start_time` is recorded in an internal `state` dictionary.
2. `Base.metadata.create_all()` is executed:

   * Ensures all database tables exist.
   * No migrations are run; this is schema verification only.
3. Application begins accepting requests.

No shutdown logic is currently defined.

---

## Authentication

### Protected Routes

Routes marked with 🔒 require authentication and are decorated with:

```python
@requires_auth
```

### How Authentication Works

1. Client sends:

   ```
   Authorization: Bearer <Clerk JWT>
   ```
2. Middleware:

   * Verifies the token using Clerk configuration.
   * Extracts user claims.
   * Stores them on:

     ```
     request.state.user
     ```
3. Route handlers read user data from `request.state.user`.

### Required Claims

Some routes (notably product creation) **require an email address** in the token claims.
If `email` is missing, the request will fail with a 400 error.

---

## CORS Configuration

* Allowed origins are restricted to:

  * `FRONTEND_URL` from environment variables
  * Defaults to `http://localhost:3000`
* Credentials, all methods, and all headers are allowed.

Wildcard (`*`) is intentionally avoided.

---

## API Routes

---

### 1. System Status

**`GET /`**

Returns API health status and uptime.

#### Logic Flow

1. Reads `start_time` from application state.
2. Calculates uptime in seconds.
3. Returns a minimal health payload.

#### Response

```json
{
  "status": "ok",
  "uptime_seconds": 183
}
```

---

### 2. CDN Authentication 🔒

**`GET /api/cdn-auth`**

Returns ImageKit authentication parameters for client-side uploads.

#### Purpose

Allows the frontend to upload images directly to ImageKit without exposing private keys.

#### Logic Flow

1. Authentication middleware verifies the request.
2. Backend calls:

   ```python
   imagekit.get_authentication_parameters()
   ```
3. ImageKit returns:

   * `signature`
   * `token`
   * `expire`
4. These values are forwarded directly to the client.

No database or cache interaction occurs.

---

### 3. List Products

**`GET /api/product`**

Returns a paginated list of products with optional search and Redis caching.

#### Query Parameters

| Name    | Type   | Default  | Constraints |
| ------- | ------ | -------- | ----------- |
| `q`     | string | optional | Search term |
| `page`  | int    | 1        | Must be ≥ 1 |
| `limit` | int    | 20       | Max 100     |

---

#### Caching Strategy

This endpoint uses a **cache-aside** pattern.

##### Cache Key Format

* Without search:

  ```
  products:all:page:{page}:limit:{limit}
  ```
* With search:

  ```
  products:search:{q}:page:{page}:limit:{limit}
  ```

---

#### Logic Flow

1. **Offset Calculation**

   ```
   offset = (page - 1) * limit
   ```

2. **Redis Cache Lookup**

   * If cached data exists:

     * Deserialize into `ProductListWrapper`
     * Return immediately

3. **Database Query (Cache Miss)**

   * Base query:

     ```
     SELECT * FROM products
     ```
   * If `q` is provided:

     * Apply `ILIKE` filter to `name` and `description`
   * Apply `OFFSET` and `LIMIT`

4. **Cache Population**

   * Response is serialized using Pydantic
   * Stored in Redis with a **1 hour TTL**

5. **Response**

   * Returns `ProductListWrapper`

---

### 4. Create Product 🔒

**`POST /api/product`**

Creates a new product listing and associates it with the authenticated user.

#### Request Body

`ProductRequest`
Includes fields such as:

* `name`
* `description`
* `price`
* `category`
* `image_url`

---

#### Logic Flow

1. **Authentication**

   * User claims are read from `request.state.user`.

2. **User Email Validation**

   * Email is required.
   * If missing:

     * Request fails with `400 Bad Request`.

3. **Lazy User Synchronization**

   * Query `UserDB` by email.
   * If user does not exist:

     * Create a new local user record.
     * Commit and refresh.

4. **Product Creation**

   * Product payload is unpacked.
   * `owner_id` is injected from the resolved user.
   * Product is inserted and committed.

5. **Cache Invalidation**

   * All keys matching:

     ```
     products:*
     ```

     are deleted.
   * Errors during cache invalidation are logged but **do not fail the request**.

6. **Response**

   * Returns `SingleProductWrapper`
   * HTTP status: `201 Created`

---

#### Error Handling

* `401` – Authentication failure
* `400` – Missing email in token
* `500` – Database or server error (with rollback)

Errors return a structured JSON body.

---

### 5. Get Product Details

**`GET /api/product/{product_id}`**

Returns a single product and all associated reviews.

#### Path Parameters

| Name         | Type |
| ------------ | ---- |
| `product_id` | int  |

---

#### Logic Flow

1. **Fetch Product**

   * Uses `db.get(ProductDB, product_id)`.

2. **Not Found Handling**

   * If product does not exist:

     * Returns `404` with structured error payload.

3. **Fetch Reviews**

   * Queries `ReviewDB` where:

     ```
     item_id == product_id
     ```

4. **Aggregation**

   * Combines product and reviews into `ProductInfoWithReviews`.

5. **Response**

   * Wrapped in `ProductDetailsWrapper`.

---

### 6. Get Cart 🔒 (WIP)

**`GET /api/cart`**

#### Status

Not implemented (`pass`).

#### Intended Direction

* Retrieve authenticated user’s cart
* Likely future components:

  * Cart table
  * Cart items table
  * Optional Redis session storage

---

### 7. Contact Form (WIP)

**`POST /api/contact`**

#### Status

Not implemented (`pass`).

#### Intended Direction

* Accept contact submissions
* Forward via email or persist in database

---

## Error Handling

### Standard Error Format

All structured errors follow this schema:

```json
{
  "message": "Human-readable explanation",
  "error_code": "INTERNAL_ERROR_IDENTIFIER"
}
```

### Implementation Notes

* Errors are wrapped inside `HTTPException.detail` as JSON.
* `Content-Type` is explicitly set to `application/json`.
* Database transactions are rolled back on failure where applicable.

---

## Implementation Notes & Caveats

* Swagger and ReDoc are intentionally disabled.
* Redis `KEYS` is used for cache invalidation:

  * Acceptable for now
  * Should be replaced with `SCAN` at scale
* User records are created lazily on first write.
* Product listing cache is **fully invalidated** on any product creation.
