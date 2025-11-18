import time
from fastapi import FastAPI, HTTPException, status
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from models import Base, UserDB, ProductDB
from dotenv import load_dotenv
from imagekitio import ImageKit
import os
from fastapi.middleware.cors import CORSMiddleware
from structs import ProductRequest

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "*"],  # your frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Storing the server start time, for any time calculations
start_time = time.time()
load_dotenv()


# ImageKit setup
imagekit = ImageKit(
    private_key=os.getenv("IMAGE_KIT_PRIVATE_KEY"),
    public_key=os.getenv("IMAGE_KIT_PUBLIC_KEY"),
    url_endpoint=os.getenv("IMAGE_KIT_URL")
)


# Setting up Database
url = os.getenv("TURSO_DATABASE_URL")
auth_token = os.getenv("TURSO_AUTH_TOKEN")

engine = create_engine(
    f"sqlite+{url}?secure=true",
    connect_args={
        "auth_token": auth_token,
    },
)

session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


# NOTE:Temperory veriable to store all product list
all_products = ""


@app.get("/")
def system_status():
    """
        Default route, display system status when visited
    """
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - start_time),
    }


@app.get("/api/cdn-auth")
def get_cdn_auth():
    """
        This route provides the auth signature for image uploading to CDN
    """
    return imagekit.get_authentication_parameters()


@app.get("/admin/init_db")
def init_db():
    # db.execute("select * from products").fetchall()
    return {"message": "DB created"}


@app.get("/api/product")
def get_all_products(q: str = None):
    """
    Fetches all ProductDB records from the database.
        Query parameter:
            q: Search parameter
    """
    # select all the products from db and cache them
    stmt = select(ProductDB)
    with session() as ses:
        all_products_list = ses.scalars(stmt).all()

    return all_products_list


@app.get("/api/product/{product_id}")
def get_product(product_id: int, section: str = 'details'):
    """
        Route to get details of a single product if product_id is provided.
        Query parameter:
            section: active section of product page (details, reviews, gallery)
    """
    pass


@app.post("/api/product")
def post_product(product_data: ProductRequest):
    """
        Route to create a new product.
    """
    # Authenticate user
    db_product = ProductDB(**product_data.model_dump())

    with session() as db:
        try:
            db.add(db_product)
            db.commit()
            db.refresh(db_product)

        except Exception as e:
            # Handle potential DB errors (e.g., owner_id not found)
            db.rollback()
            # Log the error
            print(f"Database error during product creation: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not create product. Check if the owner_id is valid."
            )
    # Get product from request
# Validate product data
# Add product to DB
# Commit DB and Sync DB
    return db_product


@app.get("/api/cart")
def get_cart():
    """
        Route to get products in cart of a user.
    """
    pass


@app.post("/api/contact")
def post_contact():
    """
        Route to handle the contact messages.
        Forwards the contact messages to the Developer's email.
    """
    pass
