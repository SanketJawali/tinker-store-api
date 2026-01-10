# TinkerStore Backend API Documentation

This document describes the **current implementation** of the TinkerStore backend API, including request flow, authentication behavior, caching strategy, and error handling.

The backend is built with **FastAPI**, persists data in **Turso (SQLite)** via SQLAlchemy ORM, uses **Redis** for caching, and integrates **Clerk** for authentication and **ImageKit** for media uploads.

---

## Architecture Overview

### Core Technologies

* **Framework**: FastAPI
* **Database**: SQLite (Turso) via SQLAlchemy ORM
* **Caching**: Redis (Redis Cloud) with cache-aside pattern
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
3. **Redis Connection**:
   * Connects to Redis using environment variables:
     * `REDIS_URL` (host)
     * `REDIS_PORT` (port, default 14027 for Redis Cloud)
     * `REDIS_USERNAME` (default: "default")
     * `REDIS_PASSWORD`
   * Connection is tested with `ping()`.
   * Redis client is stored in `app.state.redis` for dependency injection.
4. Application begins accepting requests.

### Shutdown

On application shutdown:

* Redis connection is closed gracefully.
* All pending database transactions are finalized.

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
   * Stores them on `request.state.user`.
3. Route handlers read user data from `request.state.user`.

### Required Claims

Some routes (notably product creation, cart operations, and reviews) **require an email address** in the token claims.
If `email` is missing, the request will fail with a 400 error.

### User Synchronization

Users are created **lazily** on their first write operation:
* When a user creates a product, adds to cart, or submits a review
* A local `UserDB` record is created if one doesn't exist
* Subsequent requests reuse the existing record

---

## CORS Configuration

* Allowed origins are restricted to:
  * `FRONTEND_URL` from environment variables
  * Defaults to `http://localhost:3000`
* Credentials, all methods, and all headers are allowed.
* Wildcard (`*`) is intentionally avoided.

---

## Caching Strategy

### Cache-Aside Pattern

The application implements a **cache-aside** (lazy-loading) caching pattern:

1. **On Read**: Check Redis → if miss, query DB → populate cache → return
2. **On Write**: Execute DB operation → invalidate related cache keys → return
3. **TTL**: Product list cache expires after 1 hour

### Cache Invalidation

When a new product is created:
* All keys matching `products:*` are deleted
* This ensures fresh data on the next product list request
* Invalidation errors are logged but do not fail the request

---

## API Routes

---

### 1. System Status

**`GET /`**

Returns API health status and uptime.

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

#### Response

```json
{
  "signature": "...",
  "token": "...",
  "expire": 1234567890
}
```

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

#### Cache Key Format

* Without search: `products:all:page:{page}:limit:{limit}`
* With search: `products:search:{q}:page:{page}:limit:{limit}`
* **TTL**: 1 hour (3600 seconds)

#### Logic Flow

1. Calculate offset: `offset = (page - 1) * limit`
2. Check Redis cache using granular cache key
3. If cache hit: deserialize and return
4. If cache miss:
   * Query database with filters and pagination
   * Apply `ILIKE` search on `name` and `description` if `q` is provided
   * Serialize response using Pydantic
   * Store in Redis with 1-hour TTL
   * Return response

#### Response

```json
{
  "success": true,
  "message": "Successfully retrieved product list.",
  "data": [
    {
      "id": 1,
      "name": "Product Name",
      "price": 2999,
      "description": "...",
      "category": "Electronics",
      "stock": 50,
      "image_url": "https://...",
      "owner_id": 1
    }
  ]
}
```

#### Error Handling

* `500` – Server error (with error code and message)

---

### 4. Create Product 🔒

**`POST /api/product`**

Creates a new product listing and associates it with the authenticated user.

#### Request Body

```json
{
  "name": "New Product",
  "price": 2999,
  "description": "Product description",
  "category": "Electronics",
  "stock": 50,
  "image_url": "https://..."
}
```

#### Logic Flow

1. Extract user email from token claims (required)
2. Resolve or create `UserDB` record using email (lazy sync)
3. Inject `owner_id` from resolved user
4. Insert product into database
5. Invalidate all `products:*` cache keys
6. Return created product with `201 Created` status

#### Response

```json
{
  "success": true,
  "message": "Product created successfully.",
  "data": {
    "id": 5,
    "name": "New Product",
    "price": 2999,
    "description": "...",
    "category": "Electronics",
    "stock": 50,
    "image_url": "https://...",
    "owner_id": 1
  }
}
```

#### Error Handling

* `400` – Missing email in token claims
* `401` – Authentication failure
* `500` – Database error (with rollback)

---

### 5. Get Product Details

**`GET /api/product/{product_id}`**

Returns a single product and all associated reviews.

#### Path Parameters

| Name         | Type |
| ------------ | ---- |
| `product_id` | int  |

#### Logic Flow

1. Fetch product by ID
2. If not found: return 404 with structured error
3. Query all reviews for this product
4. Combine product and reviews into response
5. Return aggregated data

#### Response

```json
{
  "success": true,
  "message": "Product 1 retrieved successfully.",
  "data": {
    "product": {
      "id": 1,
      "name": "Product Name",
      "price": 2999,
      "description": "...",
      "category": "Electronics",
      "stock": 50,
      "image_url": "https://...",
      "owner_id": 1
    },
    "reviews": [
      {
        "id": 1,
        "product_id": 1,
        "user_id": 2,
        "rating": 5,
        "content": "Great product!",
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:30:00Z"
      }
    ]
  }
}
```

#### Error Handling

* `404` – Product not found
* `500` – Server error

---

### 6. Get Cart 🔒

**`GET /api/cart`**

Retrieves all items in the authenticated user's cart.

#### Logic Flow

1. Extract user email from token claims (required)
2. Resolve `UserDB` by email
3. If user doesn't exist: return empty cart
4. Query `CartDB` joined with `ProductDB` to get product details
5. Format results into `CartItem` objects with product info and quantity
6. Return cart items list

#### Response

```json
{
  "success": true,
  "message": "Cart retrieved successfully.",
  "data": [
    {
      "cart_id": 1,
      "product_id": 5,
      "name": "Product Name",
      "price": 2999,
      "image_url": "https://...",
      "category": "Electronics",
      "quantity": 2
    }
  ]
}
```

#### Error Handling

* `400` – Missing email in token claims
* `500` – Server error

---

### 7. Add/Update Cart Item 🔒

**`POST /api/cart`**

Adds a new item to the cart or updates quantity of an existing item.

#### Request Body

```json
{
  "cart_id": null,
  "product_id": 5,
  "quantity": 2
}
```

| Field        | Type    | Description |
| ------------ | ------- | ----------- |
| `cart_id`    | int\|null | Optional: specific cart entry to update |
| `product_id` | int     | Product to add (required) |
| `quantity`   | int     | Quantity to add (required) |

#### Logic Flow

1. Extract user email and resolve `UserDB` (lazy sync if needed)
2. Validate product exists in database
3. Validate quantity is not zero
4. Search for existing cart entry:
   * If `cart_id` provided: verify it belongs to user and matches product
   * Otherwise: search by user + product combination
5. If existing entry found:
   * Increment quantity by requested amount
   * If new quantity ≤ 0: delete entry
6. If no existing entry and quantity > 0:
   * Create new `CartDB` record
7. Commit and return result

#### Response

```json
{
  "success": true,
  "message": "Item added to cart successfully.",
  "data": {
    "cart_id": 1,
    "product_id": 5,
    "quantity": 2
  }
}
```

#### Error Handling

* `400` – Missing email, invalid quantity (0), or missing product_id
* `401` – Authentication failure
* `404` – Product not found
* `500` – Server error (with rollback)

---

### 8. Create Review 🔒

**`POST /api/review`**

Submits a new review for a product.

#### Request Body

```json
{
  "product_id": 1,
  "title": "Great quality!",
  "rating": 5,
  "content": "This product exceeded my expectations. Highly recommended!"
}
```

| Field        | Type | Constraints |
| ------------ | ---- | ----------- |
| `product_id` | int  | Must exist  |
| `title`      | str  | Max 200 chars |
| `rating`     | int  | 1–5 only |
| `content`    | str  | Max 1000 chars |

#### Logic Flow

1. Extract user email from token claims (required)
2. Validate product exists (404 if not)
3. Resolve or create `UserDB` by email (lazy sync)
4. Create `ReviewDB` record with:
   * `product_id` from request
   * `user_id` from resolved user
   * Review metadata (title, rating, content)
   * Auto-populated timestamps (`created_at`, `updated_at`)
5. Flush to generate primary key
6. Commit and return review with ID

#### Response

```json
{
  "success": true,
  "message": "Successfully added new review.",
  "data": {
    "id": 1,
    "title": "Great quality!",
    "rating": 5,
    "content": "This product exceeded my expectations..."
  }
}
```

#### Error Handling

* `400` – Missing email in token claims
* `401` – Authentication failure
* `404` – Product not found
* `500` – Server error (with rollback)

---

### 9. Contact Form (WIP)

**`POST /api/contact`**

#### Status

Not yet implemented.

#### Intended Purpose

* Accept contact/inquiry submissions from users
* Potential actions:
  * Persist in database
  * Forward via email to admin
  * Trigger notification workflow

---

## Error Handling

### Standard Error Format

All errors follow this JSON schema:

```json
{
  "success": false,
  "message": "Human-readable explanation",
  "error_code": "INTERNAL_ERROR_IDENTIFIER"
}
```

### Error Response Headers

* `Content-Type: application/json` is explicitly set on all error responses.

### Error Codes

Common error codes include:

| Code | Scenario |
| ---- | -------- |
| `MISSING_EMAIL` | Email not in token claims |
| `PRODUCT_NOT_FOUND` | Product ID does not exist |
| `INVALID_QUANTITY` | Quantity is zero or invalid |
| `MISSING_PRODUCT_ID` | Product ID not provided in request |
| `DB_CREATE_ERROR` | Database insert failed |
| `SERVER_FETCH_ERROR` | Server error during retrieval |
| `REVIEW_PROCESSING_ERROR` | Error while creating review |

### Transaction Rollback

Database transactions are automatically rolled back on error for:
* Product creation
* Cart operations
* Review creation

---

## Implementation Notes & Caveats

* **Swagger & ReDoc**: Intentionally disabled for this API.
* **Cache Invalidation**: Uses `KEYS` pattern matching. At scale, should be replaced with `SCAN`.
* **Lazy User Sync**: Users are created on first write, not on first login.
* **Full Cache Invalidation**: Product list cache is completely cleared on any product creation. Consider granular invalidation strategies as scale increases.
* **Redis Dependency**: If Redis connection fails, the app continues but caching is unavailable.
* **No Backward Relationships**: `UserDB` does not maintain a `back_populates` to products/reviews for performance reasons.

---

## Environment Variables

```env
# Database (Turso)
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...

# Authentication (Clerk)
CLERK_SECRET_KEY=...
CLERK_ISSUER=...

# Media (ImageKit)
IMAGE_KIT_PRIVATE_KEY=...
IMAGE_KIT_PUBLIC_KEY=...
IMAGE_KIT_URL=...

# Cache (Redis Cloud)
REDIS_URL=redis://...
REDIS_PORT=14027
REDIS_USERNAME=default
REDIS_PASSWORD=...

# Frontend
FRONTEND_URL=http://localhost:3000

# Optional
GROQ_API_KEY=...
```
