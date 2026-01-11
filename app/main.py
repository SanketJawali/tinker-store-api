import time
import os
import logging
from contextlib import asynccontextmanager
from typing import Generator, List

from fastapi import FastAPI, HTTPException, status, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, select, or_, text
from sqlalchemy.orm import sessionmaker, Session
from pydantic_settings import BaseSettings
from redis import Redis  # Changed from redis.asyncio import Redis

# Custom imports
# Import ReviewDB for query
from app.lib.models import Base, UserDB, ProductDB, ReviewDB, CartDB, OrderDB, OrderItemDB
from app.lib.base_models import Product, Review, CartItem, OrderSummary, User
from app.lib.request_models import ProductRequest, ReviewRequest, CheckoutRequest
from app.lib.response_models import (
    ProductListWrapper,
    SingleProductWrapper,
    ProductDetailsWrapper,
    APIErrorResponse,
    ProductInfoWithReviews,
    NewCartItem,
    NewCartItemWrapper,
    CartListWrapper,
    ReviewResponse,
    ReviewResponseWrapper,
    CheckoutResponse
)
from app.lib.auth import requires_auth, require_admin
from app.lib.observability import (
    record_cache_hit,
    record_cache_miss,
    get_cache_metrics,
    log_cache_hit_rate,
)
from imagekitio import ImageKit


# --- Configuration ---
class Settings(BaseSettings):
    # Existing Fields
    TURSO_DATABASE_URL: str
    TURSO_AUTH_TOKEN: str
    IMAGE_KIT_PRIVATE_KEY: str
    IMAGE_KIT_PUBLIC_KEY: str
    IMAGE_KIT_URL: str

    # NEW FIELDS ADDED TO RESOLVE VALIDATION ERROR
    CLERK_SECRET_KEY: str
    CLERK_ISSUER: str
    GROQ_API_KEY: str  # Include this since it was in your .env and caused an error

    # Frontend URL for CORS
    FRONTEND_URL: str = "http://localhost:3000"

    # Redis cache
    REDIS_URL: str
    REDIS_PORT: str
    REDIS_USERNAME: str
    REDIS_PASSWORD: str

    class Config:
        env_file = ".env"


settings = Settings()
logger = logging.getLogger("uvicorn")

# --- Database Setup (Unchanged) ---
engine = create_engine(
    f"sqlite+{settings.TURSO_DATABASE_URL}?secure=true",
    connect_args={"auth_token": settings.TURSO_AUTH_TOKEN},
    echo=False
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- ImageKit Setup ---
# Updated initialization based on new SDK docs (only private_key required)
imagekit = ImageKit(
    private_key=settings.IMAGE_KIT_PRIVATE_KEY
)

# --- Lifespan & App Setup ---
# Stores app state (like start time) without polluting global namespace
state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB and capture start time
    state["start_time"] = time.time()
    try:
        logger.info("Connecting to Turso Database...")
        Base.metadata.create_all(bind=engine)
        logger.info("Turso Database tables verified/created.")
    except Exception as e:
        logger.error(f"Turso Database initialization error: {e}")

    # Startup: Check Redis cache connection
    logger.info("Connecting to Redis cache...")
    # 1. Initialize Redis ONCE
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_client = Redis(
        host=redis_url,
        port=14027,
        username=os.getenv("REDIS_USERNAME", "default"),
        password=os.getenv("REDIS_PASSWORD", ""),
        decode_responses=True  # Optional: makes output str instead of bytes
    )

    # 2. Check Connection
    try:
        redis_client.ping()  # Removed await, sync call
        logger.info("Redis cache connected successfully!")

        # 3. Store in App State
        app.state.redis = redis_client
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        # Optional: raise e if you want the app to crash if Redis is down

    yield

    # --- SHUTDOWN ---
    redis_client.close()  # Removed await
    logger.info("Redis connection closed.")


def get_redis_client(request: Request):
    """Dependency: Retreives the persistent Redis client from app state."""
    return request.app.state.redis
    # Shutdown logic (if any) goes here


app = FastAPI(
    lifespan=lifespan,
    docs_url=None,   # Disable Swagger UI
    redoc_url=None   # Disable ReDoc
)

app.add_middleware(
    CORSMiddleware,
    # Don't use "*" in production if possible
    allow_origins=os.environ.get(
        "FRONTEND_URL", settings.FRONTEND_URL).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Routes ---
@app.get("/")
def system_status(request: Request, db: Session = Depends(get_db)):
    """Display system status and uptime."""
    uptime = round(time.time() - state.get("start_time", time.time()))

    # --- DB health ---
    db_ok = False
    db_error = None
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        db_error = str(e)

    # --- Cache health ---
    cache_ok = False
    cache_error = None
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        cache_error = "Redis client not initialized"
    else:
        try:
            redis.ping()
            cache_ok = True
        except Exception as e:
            cache_error = str(e)

    cache_metrics = get_cache_metrics()
    log_cache_hit_rate(logger)

    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "database": {
            "ok": db_ok,
            "error": db_error,
        },
        "cache": {
            "ok": cache_ok,
            "error": cache_error,
            "hits": cache_metrics["hits"],
            "misses": cache_metrics["misses"],
            "total": cache_metrics["total"],
            "hit_rate_pct": cache_metrics["hit_rate_pct"],
        },
    }


@app.get("/api/cdn-auth")
@requires_auth
async def get_cdn_auth(request: Request):
    """Provides auth signature for ImageKit."""
    # Updated to use .helper namespace as per new SDK docs
    return imagekit.helper.get_authentication_parameters()


@app.get("/api/product", response_model=ProductListWrapper, tags=["Products"])
def get_all_products(
    q: str | None = None,
    page: int = Query(1, ge=1, description="Page number, starts at 1"),
    limit: int = Query(20, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis_client)
):
    """
    Fetches products with Pagination and Caching.
    """
    # 1. Calculate Offset
    offset = (page - 1) * limit

    # 2. Define Granular Cache Key
    # Structure: products:[type]:[query_if_any]:page:[num]:limit:[num]
    if q:
        cache_key = f"products:search:{q}:page:{page}:limit:{limit}"
    else:
        cache_key = f"products:all:page:{page}:limit:{limit}"

    # 3. Check Redis Cache
    cached_data = redis.get(cache_key)
    if cached_data:
        record_cache_hit()
        return ProductListWrapper.model_validate_json(cached_data)

    record_cache_miss()

    # 4. Query DB (Cache Miss)
    logger.info(f"Cache miss - fetching page {page} from DB")

    stmt = select(ProductDB)

    # Apply Search Filter if 'q' exists
    if q:
        search_filter = f"%{q}%"
        stmt = stmt.where(
            or_(
                ProductDB.name.ilike(search_filter),
                ProductDB.description.ilike(search_filter)
            )
        )

    # Apply Pagination (Offset & Limit)
    stmt = stmt.offset(offset).limit(limit)

    products = db.scalars(stmt).all()

    # 5. Create Wrapper & Cache Result
    response_wrapper = ProductListWrapper(data=products)

    # Serialize and save to Redis (1 hour TTL)
    redis.set(cache_key, response_wrapper.model_dump_json(), ex=3600)

    return response_wrapper


@app.post(
    "/api/product",
    status_code=status.HTTP_201_CREATED,
    response_model=SingleProductWrapper,
    responses={
        401: {"model": APIErrorResponse, "description": "Authentication failed"},
        500: {"model": APIErrorResponse, "description": "Database error"},
    },
    tags=["Products"]
)
@requires_auth
async def post_product(  # Changed from async def to def
    product_data: ProductRequest,
    request: Request,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis_client)  # Added Redis dependency
):
    """
    Creates a new product. Auto-links to the authenticated user.
    Invalidates product cache on success.
    """
    try:
        # 1. Get User Info from Token
        user_claims = request.state.user
        # Prefer email, fallback to sub (Clerk ID) if email is missing
        user_email = user_claims.get("email")
        user_name = user_claims.get("name") or "Unknown User"

        if not user_email:
            # If email is missing in claims, we can't reliably link to UserDB based on your schema
            raise HTTPException(
                status_code=400,
                detail=APIErrorResponse(
                    success=False,
                    message="User email not found in token claims. Ensure 'email' is in session token.",
                    error_code="MISSING_EMAIL"
                ).model_dump_json()
            )

        # 2. Resolve UserDB ID (Sync logic)
        # Check if user exists in our DB
        stmt = select(UserDB).where(UserDB.email == user_email)
        db_user = db.scalars(stmt).first()

        if not db_user:
            # User doesn't exist in local DB yet -> Create them (Lazy Sync)
            logger.info(f"Creating new local user for {user_email}")
            db_user = UserDB(name=user_name, email=user_email)
            db.add(db_user)
            db.commit()
            db.refresh(db_user)

        # 3. Create Product
        # We exclude owner_id from the incoming data (if it was there) and inject the real ID
        product_dict = product_data.model_dump()
        db_product = ProductDB(**product_dict, owner_id=db_user.id)

        db.add(db_product)
        db.commit()
        db.refresh(db_product)

        # 4. Invalidate Cache
        # Since a new product affects the main list and potentially any search query,
        # the safest approach is to clear all product-related cache keys.
        try:
            # Find all keys starting with "products:"
            # Note: In extremely high-traffic Redis instances, SCAN is preferred over KEYS.
            cache_keys = redis.keys("products:*")
            if cache_keys:
                redis.delete(*cache_keys)
                logger.info(f"Invalidated {
                            len(cache_keys)} product cache keys.")
        except Exception as e:
            # Log error but don't fail the request, as the product is already created
            logger.error(f"Cache invalidation failed: {e}")

        return SingleProductWrapper(
            data=db_product,
            message="Product created successfully."
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Database error creating product: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=APIErrorResponse(
                message="Could not create product due to a database error.",
                error_code="DB_CREATE_ERROR"
            ).model_dump_json(),
            headers={"Content-Type": "application/json"}
        )


@app.get(
    "/api/product/{product_id}",
    response_model=ProductDetailsWrapper,
    responses={
        404: {"model": APIErrorResponse, "description": "Product not found"},
        500: {"model": APIErrorResponse, "description": "Server error"},
    },
    tags=["Products"]
)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
):
    """
    Route to get details of a single product and its reviews.
    """
    try:
        cache_key = f"product:{product_id}:details"

        cached_data = None
        try:
            cached_data = redis.get(cache_key)
        except Exception as e:
            logger.warning(f"Redis get failed for {cache_key}: {e}")

        if cached_data:
            record_cache_hit()
            return ProductDetailsWrapper.model_validate_json(cached_data)

        record_cache_miss()

        # 1. Fetch the single product
        product = db.get(ProductDB, product_id)

        if not product:
            # Raise 404 with structured error response
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=APIErrorResponse(
                    message=f"Product with id {product_id} not found.",
                    error_code="PRODUCT_NOT_FOUND"
                ).model_dump_json(),
                headers={"Content-Type": "application/json"}
            )

        # 2. Fetch all reviews for that product ID
        review_stmt = select(ReviewDB).where(ReviewDB.product_id == product_id)
        reviews = db.scalars(review_stmt).all()

        # 3. Combine product details and reviews into the structured response
        response_wrapper = ProductDetailsWrapper(
            data=ProductInfoWithReviews(product=product, reviews=reviews),
            message=f"Product {product_id} retrieved successfully."
        )

        try:
            redis.set(cache_key, response_wrapper.model_dump_json(), ex=3600)
        except Exception as e:
            logger.warning(f"Redis set failed for {cache_key}: {e}")

        return response_wrapper

    except HTTPException:
        # Re-raise explicit HTTPExceptions (like the 404 above)
        raise
    except Exception as e:
        logger.error(f"Error fetching product {product_id}: {e}")
        # Catch generic server errors and return structured 500 response
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=APIErrorResponse(
                message="An unexpected server error occurred while retrieving the product.",
                error_code="SERVER_FETCH_ERROR"
            ).model_dump_json(),
            headers={"Content-Type": "application/json"}
        )


@app.get(
    "/api/cart",
    response_model=CartListWrapper,
    tags=["Cart"]
)
@requires_auth
def get_cart(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Route to get products in cart of a user.
    """
    try:
        # 1. Get User Info from Token
        user_claims = request.state.user
        user_email = user_claims.get("email")

        if not user_email:
            raise HTTPException(
                status_code=400,
                detail=APIErrorResponse(
                    success=False,
                    message="User email not found in token claims.",
                    error_code="MISSING_EMAIL"
                ).model_dump_json()
            )

        # 2. Resolve UserDB ID
        stmt = select(UserDB).where(UserDB.email == user_email)
        db_user = db.scalars(stmt).first()

        if not db_user:
            # If user doesn't exist in DB yet, return empty list
            return CartListWrapper(
                data=[],
                message="Cart is empty."
            )

        # 3. Fetch cart items joined with Product details
        # We join CartDB and ProductDB to get the product info (name, price, image)
        # alongside the quantity from the cart.
        stmt = (
            select(CartDB, ProductDB)
            .join(ProductDB, CartDB.product_id == ProductDB.id)
            .where(CartDB.user_id == db_user.id)
        )

        results = db.execute(stmt).all()

        # 4. Format the response using the CartItem model
        cart_items: List[CartItem] = []
        for cart_entry, product_entry in results:
            cart_items.append(CartItem(
                cart_id=cart_entry.id,
                product_id=product_entry.id,
                name=product_entry.name,
                price=product_entry.price,
                image_url=product_entry.image_url,
                category=product_entry.category,
                quantity=cart_entry.quantity
            ))

        return CartListWrapper(
            data=cart_items,
            message="Cart retrieved successfully."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching cart: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=APIErrorResponse(
                success=False,
                message="An unexpected server error occurred while fetching cart.",
                error_code="SERVER_FETCH_CART"
            ).model_dump_json(),
            headers={"Content-Type": "application/json"}
        )


@app.post(
    "/api/cart",
    response_model=NewCartItemWrapper,
    tags=["Cart"]
)
@requires_auth
def post_cart(
    request: Request,
    item_data: NewCartItem,
    db: Session = Depends(get_db),
):
    """
    Route to add or update products in cart of a user.
    """
    try:
        # 1. Get User Info from Token
        user_claims = request.state.user
        # Prefer email, fallback to sub (Clerk ID) if email is missing
        user_email = user_claims.get("email")
        user_name = user_claims.get("name") or "Unknown User"

        if not user_email:
            raise HTTPException(
                status_code=400,
                detail=APIErrorResponse(
                    success=False,
                    message="User email not found in token claims.",
                    error_code="MISSING_EMAIL"
                ).model_dump_json()
            )

        if item_data.quantity == 0:
            raise HTTPException(
                status_code=400,
                detail=APIErrorResponse(
                    success=False,
                    message="Quantity cannot be zero when adding to cart.",
                    error_code="INVALID_QUANTITY"
                ).model_dump_json()
            )
        if item_data.product_id is None:
            raise HTTPException(
                status_code=400,
                detail=APIErrorResponse(
                    success=False,
                    message="Product ID must be provided when adding to cart.",
                    error_code="MISSING_PRODUCT_ID"
                ).model_dump_json()
            )

        # Check if the product exists in the DB before linking it.
        # This prevents "FOREIGN KEY constraint failed" errors.
        product_check = db.get(ProductDB, item_data.product_id)
        if not product_check:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=APIErrorResponse(
                    success=False,
                    message=f"Product with ID {
                        item_data.product_id} not found.",
                    error_code="PRODUCT_NOT_FOUND"
                ).model_dump_json()
            )

        # 2. Resolve UserDB ID (Sync logic)
        # Check if user exists in our DB
        stmt = select(UserDB).where(UserDB.email == user_email)
        db_user = db.scalars(stmt).first()

        if not db_user:
            # Lazy Sync: Create user if they don't exist locally
            logger.info(f"Creating new local user for {user_email}")
            db_user = UserDB(name=user_name, email=user_email)
            db.add(db_user)
            db.commit()
            db.refresh(db_user)

        # 3. Update Cart Logic
        item_dict = item_data.model_dump()
        target_product_id = item_dict["product_id"]
        qty_to_add = item_dict["quantity"]
        # Safe access if model updated
        target_cart_id = getattr(item_data, "cart_id", None)

        existing_cart_item = None

        # Case A: Cart ID provided - Direct lookup
        if target_cart_id:
            existing_cart_item = db.get(CartDB, target_cart_id)

            # Security ensure item belongs to user and matches product
            if existing_cart_item:
                if existing_cart_item.user_id != db_user.id:
                    # Don't reveal existence to unauthorized user
                    existing_cart_item = None
                elif existing_cart_item.product_id != target_product_id:
                    # Mismatch between cart ID and product ID provided
                    existing_cart_item = None

        # Case B: No Cart ID OR Direct lookup failed/invalid - Fallback to search by Product ID
        if existing_cart_item is None:
            user_cart_stmt = select(CartDB).where(
                CartDB.user_id == db_user.id,
                CartDB.product_id == target_product_id
            )
            existing_cart_item = db.scalars(user_cart_stmt).first()

        # 4. Perform Update or Insert
        if existing_cart_item is not None:
            # Update existing item quantity
            # NOTE: SQLAlchemy tracks changes on attached objects automatically
            existing_cart_item.quantity += qty_to_add

            if existing_cart_item.quantity <= 0:
                # Remove item if quantity is zero or negative
                db.delete(existing_cart_item)
        else:
            # Create new product entry in cart
            if qty_to_add > 0:
                db_cart_item = CartDB(
                    product_id=target_product_id,
                    quantity=qty_to_add,
                    user_id=db_user.id
                )
                db.add(db_cart_item)

        db.commit()

        return NewCartItemWrapper(
            data=item_data,
            message="Item added to cart successfully."
        )

    except HTTPException as e:
        logger.error(f"HTTP error while adding item to cart: {e.detail}")
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error occured while adding item to cart: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=APIErrorResponse(
                success=False,
                message="An unexpected server error occurred while adding item to cart.",
                error_code="SERVER_ADD_CART_ERROR"
            ).model_dump_json(),
            headers={"Content-Type": "application/json"}
        )


@app.post("/api/review",
          response_model=ReviewResponseWrapper,
          tags=["Review"]
          )
@requires_auth
def post_review(
    request: Request,
    review: ReviewRequest,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
):
    """
    Route to add a new review for a product.
    """
    try:
        user_claims = request.state.user
        user_email = user_claims.get("email")
        user_name = user_claims.get("name") or "Unknown User"

        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=APIErrorResponse(
                    success=False,
                    message="User email not found in token claims.",
                    error_code="MISSING_EMAIL",
                ).model_dump_json(),
                headers={"Content-Type": "application/json"},
            )

        # Ensure product exists before creating review
        product_id = getattr(review, "product_id", None)
        if product_id is None or db.get(ProductDB, product_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=APIErrorResponse(
                    success=False,
                    message=f"Product with id {product_id} not found.",
                    error_code="PRODUCT_NOT_FOUND",
                ).model_dump_json(),
                headers={"Content-Type": "application/json"},
            )

        # Resolve/create local user
        stmt = select(UserDB).where(UserDB.email == user_email)
        db_user = db.scalars(stmt).first()
        if not db_user:
            # Lazy Sync: Create user if they don't exist locally
            logger.info(f"Creating new local user for {user_email}")
            db_user = UserDB(name=user_name, email=user_email)
            db.add(db_user)
            db.commit()
            db.refresh(db_user)

        review_data = review.model_dump()
        review_data["user_id"] = db_user.id
        # logger.info(f"Creating review {review_data}")

        # Create and persist review
        db_review = ReviewDB(**review_data)
        db.add(db_review)

        # Flush sends INSERT so PK gets generated/populated on db_review.id
        db.flush()

        db.commit()
        db.refresh(db_review)

        # Invalidate product detail cache so new review shows up.
        try:
            redis.delete(f"product:{product_id}:details")
        except Exception as e:
            logger.warning(f"Cache invalidation failed for product {
                           product_id}: {e}")

        return ReviewResponseWrapper(
            # Prefer validating from the ORM object (requires from_attributes=True on the Pydantic model)
            data=ReviewResponse.model_validate(db_review),
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=APIErrorResponse(
                success=False,
                message=f"Error occured while processing review: {e}",
                error_code="REVIEW_PROCESSING_ERROR",
            ).model_dump_json(),
            headers={"Content-Type": "application/json"},
        )


@app.post(
    "/api/checkout",
    response_model=CheckoutResponse,
    tags=["Checkout"]
)
@requires_auth
def checkout(
    request: Request,
    checkout_data: CheckoutRequest,
    db: Session = Depends(get_db),
):
    """
    Finalizes the authenticated user's cart into an order.
    """
    try:
        user_claims = request.state.user
        user_email = user_claims.get("email")

        # 1. Fetch User Record
        stmt = select(UserDB).where(UserDB.email == user_email)
        db_user = db.scalars(stmt).first()

        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=APIErrorResponse(
                    success=False,
                    message="User not found.",
                    error_code="USER_NOT_FOUND"
                ).model_dump_json()
            )

        # 2. Fetch Cart Items
        cart_stmt = select(CartDB).where(CartDB.user_id == db_user.id)
        cart_items = db.scalars(cart_stmt).all()

        if not cart_items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=APIErrorResponse(
                    success=False,
                    message="Cart is empty.",
                    error_code="EMPTY_CART"
                ).model_dump_json()
            )

        # 3. Validate and Calculate Totals
        total_amount = 0
        order_items_data = []

        for item in cart_items:
            if item.quantity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=APIErrorResponse(
                        success=False,
                        message=f"Invalid quantity for product {
                            item.product_id}.",
                        error_code="INVALID_QUANTITY"
                    ).model_dump_json()
                )

            # Check Product
            product = db.get(ProductDB, item.product_id)
            if not product:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=APIErrorResponse(
                        success=False,
                        message=f"Product with ID {
                            item.product_id} no longer exists.",
                        error_code="PRODUCT_NOT_FOUND"
                    ).model_dump_json()
                )

            if product.stock < item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=APIErrorResponse(
                        success=False,
                        message=f"Insufficient stock for product '{product.name}'. Available: {
                            product.stock}, Requested: {item.quantity}",
                        error_code="INSUFFICIENT_STOCK"
                    ).model_dump_json()
                )

            # Accumulate Data
            price = product.price
            total_amount += price * item.quantity

            order_items_data.append({
                "product": product,
                "quantity": item.quantity,
                "price": price
            })

        # 4. Create Order
        new_order = OrderDB(
            user_id=db_user.id,
            customer_name=checkout_data.name,
            customer_address=checkout_data.address,
            customer_phone=checkout_data.phone,
            payment_method=checkout_data.payment_method,
            total_amount=total_amount,
            status="completed"
        )
        db.add(new_order)
        db.flush()

        # 5. Create Order Items & Update Stock
        for item_data in order_items_data:
            product = item_data["product"]
            quantity = item_data["quantity"]
            price_at_purchase = item_data["price"]

            # Decrease Stock
            product.stock -= quantity
            db.add(product)

            # Create Order Item
            order_item = OrderItemDB(
                order_id=new_order.id,
                product_id=product.id,
                quantity=quantity,
                price_at_purchase=price_at_purchase
            )
            db.add(order_item)

        # 6. Clear Cart
        for item in cart_items:
            db.delete(item)

        # 7. Commit
        db.commit()
        db.refresh(new_order)

        # Calculate item count for summary
        item_count = sum(item["quantity"] for item in order_items_data)

        summary = OrderSummary(
            order_id=new_order.id,
            total_amount=new_order.total_amount,
            item_count=item_count,
            created_at=new_order.created_at
        )

        return CheckoutResponse(
            data=summary
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Checkout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=APIErrorResponse(
                success=False,
                message="An unexpected error occurred during checkout.",
                error_code="CHECKOUT_ERROR"
            ).model_dump_json(),
            headers={"Content-Type": "application/json"}
        )
