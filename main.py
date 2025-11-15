from fastapi import FastAPI
import libsql
from dotenv import load_dotenv
import os


app = FastAPI()

# Setting up Turso Database
load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
auth_token = os.getenv("TURSO_AUTH_TOKEN")

conn = libsql.connect("tinkerStore.db", sync_url=url, auth_token=auth_token)
conn.sync()


@app.get("/")
def root():
    """
        Default route. Sends a Hello message
    """
    return {"message": "Hello world"}


@app.get("/api/item")
def get_all_items():
    """
        Route to get all the items from the database.
    """
    pass


@app.get("/api/item/{item_id}")
def get_item(item_id: int):
    """
        Route to get details of a single item if item_id is provided.
    """
    pass


@app.post("/api/item")
def post_item():
    """
        Route to create a new item.
    """
    pass


@app.get("/api/cart")
def get_cart():
    """
        Route to get cart items of a user.
    """
    pass


@app.post("/api/contact")
def post_contact():
    """
        Route to handle the contact messages.
        Forwards the contact messages to the Developer's email.
    """
    pass
