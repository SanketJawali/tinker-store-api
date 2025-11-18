import time
from fastapi import FastAPI
import libsql
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

start_time = time.time()
load_dotenv()


# ImageKit setup
imagekit = ImageKit(
    private_key=os.getenv("IMAGE_KIT_PRIVATE_KEY"),
    public_key=os.getenv("IMAGE_KIT_PUBLIC_KEY"),
    url_endpoint=os.getenv("IMAGE_KIT_URL")
)


# Setting up Turso Database
url = os.getenv("TURSO_DATABASE_URL")
auth_token = os.getenv("TURSO_AUTH_TOKEN")

remote_url = f"{url}?authToken={auth_token}"

db = libsql.connect("tinkerStore.db", sync_url=url, auth_token=auth_token)

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
        "version": "1.0.0"
    }


@app.get("/api/cdn-auth")
def get_cdn_auth():
    """
        This route provides the auth signature for image uploading to CDN
    """
    auth = imagekit.get_authentication_parameters()
    return auth


@app.get("/admin/init_db")
def init_db():
    print(db.execute('''
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL CHECK (length(name) <= 50),
    description TEXT NOT NULL CHECK (length(description) <= 500),
    price REAL NOT NULL,
    category TEXT NOT NULL,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    image_url TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
          '''))

    db.execute("select * from products").fetchall()
    return {"message": "DB created"}


@app.get("/api/product")
def get_all_products(q: str = None):
    """
        Route to get all the products from the database.
        Query parameter:
            q: Search parameter
    """
    return {"success": "ok", "message": "", "data": dict(all_products)}


@app.get("/api/product/{product_id}")
def get_product(product_id: int, section: str = 'details'):
    """
        Route to get details of a single product if product_id is provided.
        Query parameter:
            section: active section of product page (details, reviews, gallery)
    """
    pass


@app.post("/api/product")
def post_product(product: ProductRequest):
    """
        Route to create a new product.
    """
    # Authenticate user

    # Get product from request
    query = """
    INSERT INTO products (
        owner_id,
        name,
        description,
        price,
        category,
        stock,
        image_url
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """

    params = (
        product.owner_id,
        product.name,
        product.description,
        product.price,
        product.category,
        product.stock,
        product.image_url
    )

    result = db.execute(query, params)
    print("Inserted row ID:", result)
# Validate product data
# Add product to DB
# Commit DB and Sync DB
    return {"message": "success"}


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
