import time
import os
import logging
from contextlib import asynccontextmanager
from typing import Generator

from fastapi import FastAPI, HTTPException, status, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, select, or_
from sqlalchemy.orm import sessionmaker, Session
from pydantic_settings import BaseSettings
from redis import Redis  # Changed from redis.asyncio import Redis

# Custom imports
# Import ReviewDB for query
from app.lib.models import Base, UserDB, ProductDB, ReviewDB
from app.lib.structs import (
    ProductRequest,
    ProductListWrapper,
    SingleProductWrapper,
    ProductDetailsWrapper,
    APIErrorResponse,
    ProductInfoWithReviews,
    Product,
    Review
)
from app.lib.auth import requires_auth, require_admin
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
imagekit = ImageKit(
    private_key=settings.IMAGE_KIT_PRIVATE_KEY,
    # public_key=settings.IMAGE_KIT_PUBLIC_KEY,
    # url_endpoint=settings.IMAGE_KIT_URL
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
    # docs_url=None,   # Disable Swagger UI
    # redoc_url=None   # Disable ReDoc
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
def system_status():
    """Display system status and uptime."""
    uptime = round(time.time() - state.get("start_time", time.time()))
    return {
        "status": "ok",
        "uptime_seconds": uptime,
    }


@app.get("/api/cdn-auth")
@requires_auth
async def get_cdn_auth(request: Request):
    """Provides auth signature for ImageKit."""
    return imagekit.get_authentication_parameters()


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
        return ProductListWrapper.model_validate_json(cached_data)

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
                detail="User email not found in token claims. Ensure 'email' is in session token."
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
def get_product(product_id: int, db: Session = Depends(get_db)):
    """
    Route to get details of a single product and its reviews.
    """
    try:
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
        review_stmt = select(ReviewDB).where(ReviewDB.item_id == product_id)
        reviews = db.scalars(review_stmt).all()

        # 3. Combine product details and reviews into the structured response
        return ProductDetailsWrapper(
            data=ProductInfoWithReviews(product=product, reviews=reviews),
            message=f"Product {product_id} retrieved successfully."
        )

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


@app.get("/api/cart")
def get_cart():
    """
    Route to get products in cart of a user.
    """
    pass


@app.post("/api/cart")
def post_cart():
    """
    Route to add products to cart of a user.
    """
    pass


@app.post("/api/new_review")
def post_new_review():
    """
    Route to add a new review for a product.
    """
    pass


@app.post("/api/contact")
def post_contact():
    """
    Route to handle the contact messages.
    Forwards the contact messages to the Developer's email.
    """
    pass
