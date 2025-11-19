import time
import logging
from contextlib import asynccontextmanager
from typing import Generator

from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session
from pydantic_settings import BaseSettings

# Custom imports
from models import Base, ProductDB
from structs import ProductRequest
from auth import requires_auth
from imagekitio import ImageKit


# --- Configuration ---
class Settings(BaseSettings):
    TURSO_DATABASE_URL: str
    TURSO_AUTH_TOKEN: str
    IMAGE_KIT_PRIVATE_KEY: str
    IMAGE_KIT_PUBLIC_KEY: str
    IMAGE_KIT_URL: str

    class Config:
        env_file = ".env"


settings = Settings()
logger = logging.getLogger("uvicorn")

# --- Database Setup ---
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
    public_key=settings.IMAGE_KIT_PUBLIC_KEY,
    url_endpoint=settings.IMAGE_KIT_URL
)

# --- Lifespan & App Setup ---
# Stores app state (like start time) without polluting global namespace
state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB and capture start time
    state["start_time"] = time.time()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created.")
    yield
    # Shutdown logic (if any) goes here

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
def get_cdn_auth():
    """Provides auth signature for ImageKit."""
    return imagekit.get_authentication_parameters()


@app.get("/api/product")
def get_all_products(q: str | None = None, db: Session = Depends(get_db)):
    """
    Fetches all products.
    TODO: Implement 'q' search filtering logic.
    """
    stmt = select(ProductDB)

    # Example of implementing the search param 'q' if needed:
    # if q:
    #     stmt = stmt.where(ProductDB.name.contains(q))

    products = db.scalars(stmt).all()
    return products


@app.post("/api/product", status_code=status.HTTP_201_CREATED)
@requires_auth
def post_product(product_data: ProductRequest, db: Session = Depends(get_db)):
    """
    Creates a new product.
    """
    # 1. Validate & Map: Pydantic (ProductRequest) has already validated types here.
    # We map the request model to the DB model.
    db_product = ProductDB(**product_data.model_dump())

    try:
        # 2. Add to Session
        db.add(db_product)

        # 3. Commit & Refresh
        db.commit()
        db.refresh(db_product)

        return db_product

    except Exception as e:
        db.rollback()
        logger.error(f"Database error creating product: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the product."
        )


@app.get("/api/product/{product_id}")
def get_product(product_id: int, section: str = 'details'):
    pass


@app.get("/api/cart")
def get_cart():
    pass


@app.post("/api/contact")
def post_contact():
    pass
