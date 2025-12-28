# TinkerStore API Documentation

This directory contains the core application logic for the TinkerStore backend. The API is built using **FastAPI** and utilizes **Turso (SQLite)** for persistence and **Redis** for caching.

## Base Configuration

*   **Database**: SQLite (via Turso) using SQLAlchemy ORM.
*   **Caching**: Redis (Redis Cloud) for caching product lists.
*   **Authentication**: Clerk (JWT verification via middleware).
*   **Media**: ImageKit.io for image hosting(CDN).

---

## Authentication

Routes marked with 🔒 require an `Authorization` header containing a valid Bearer token from Clerk.
The middleware extracts user claims and injects them into `request.state.user`.

---

## API Routes

### 1. System Status
**`GET /`**

Returns the health status and uptime of the API.

*   **Logic Flow**:
    1.  Calculates the difference between the current time and the `start_time` stored in the global `state` dictionary during application startup (`lifespan`).
*   **Response**:
    ```json
    {
      "status": "ok",
      "uptime_seconds": 120
    }
    ```

### 2. CDN Authentication 🔒
**`GET /api/cdn-auth`**

Generates authentication parameters for the frontend to upload images directly to ImageKit.

*   **Logic Flow**:
    1.  Validates user authentication.
    2.  Calls the ImageKit SDK to generate a signature, token, and timestamp.
    3.  Returns these credentials so the frontend can perform secure client-side uploads without exposing private keys.

### 3. List Products
**`GET /api/product`**

Fetches a paginated list of products. Supports search and caching.

*   **Parameters**:
    *   `q` (optional): Search string for product name or description.
    *   `page` (default: 1): Page number.
    *   `limit` (default: 20): Items per page.
*   **Logic Flow (Cache-Aside Pattern)**:
    1.  **Key Generation**: Creates a unique Redis key based on query params (e.g., `products:search:phone:page:1:limit:20`).
    2.  **Cache Check**: Queries Redis. If data exists, returns it immediately (fast path).
    3.  **Database Query**: If cache miss:
        *   Calculates SQL `OFFSET`.
        *   Filters by `q` (using `ILIKE` for case-insensitive search) if provided.
        *   Fetches records from Turso DB.
    4.  **Cache Set**: Serializes the result and saves it to Redis with a 1-hour TTL (Time To Live).
    5.  **Response**: Returns the data wrapper.

### 4. Create Product 🔒
**`POST /api/product`**

Creates a new product listing.

*   **Body**: `ProductRequest` (name, description, price, category, image_url, etc.)
*   **Logic Flow**:
    1.  **User Resolution**: Extracts the email from the auth token.
    2.  **Lazy User Sync**: Checks if the user exists in the local `UserDB`. If not, creates a local user record using the data from the token.
    3.  **Creation**: Inserts the new product into `ProductDB`, linking it to the resolved local User ID.
    4.  **Cache Invalidation**: Deletes all Redis keys matching `products:*`. This ensures that the "List Products" endpoint doesn't serve stale data missing the new item.
*   **Response**: `SingleProductWrapper` containing the created product.

### 5. Get Product Details
**`GET /api/product/{product_id}`**

Retrieves a specific product and its associated reviews.

*   **Parameters**: `product_id` (integer)
*   **Logic Flow**:
    1.  **Fetch Product**: Queries `ProductDB` by ID.
    2.  **Error Handling**: If not found, raises a 404 exception with a structured error message.
    3.  **Fetch Reviews**: Queries `ReviewDB` for all reviews linked to this `item_id`.
    4.  **Aggregation**: Combines the product object and the list of reviews into a single response object (`ProductInfoWithReviews`).

### 6. Get Cart (WIP)
**`GET /api/cart`**

*   **Status**: Not Implemented (`pass`).
*   **Intended Logic**: Will retrieve the current user's shopping cart items.

### 7. Contact Form (WIP)
**`POST /api/contact`**

*   **Status**: Not Implemented (`pass`).
*   **Intended Logic**: Will accept contact form submissions and forward them via email or store them in the DB.

---

## Error Handling

The API uses a standardized error response format:

```json
{
  "message": "Human readable error description",
  "error_code": "INTERNAL_CODE_FOR_DEBUG"
}
```
