from pydantic import BaseModel, Field, conint, EmailStr
from typing import Optional
from datetime import datetime


# --- DATABASE MODEL SCHEMAS (MAPPING to SQLAlchemy Models) ---
class User(BaseModel):
    id: int = Field(..., description="Unique user identifier.")
    name: str = Field(..., max_length=100, description="User's full name.")
    email: EmailStr = Field(..., max_length=100,
                            description="Unique user email address.")

    class Config:
        from_attributes = True


class Product(BaseModel):
    id: int = Field(..., description="Unique product identifier.")
    name: str = Field(..., max_length=100, description="Product name.")
    price: int = Field(..., gt=0, description="Price.")
    description: str = Field(..., description="Detailed product description.")
    category: str = Field(..., max_length=50, description="Product category.")
    stock: int = Field(..., ge=0, description="Current stock quantity.")
    image_url: str = Field(..., max_length=255,
                           description="URL of the product image.")
    owner_id: int = Field(...,
                          description="ID of the user who owns this product.")

    class Config:
        from_attributes = True


class Review(BaseModel):
    id: int = Field(..., description="Unique review identifier.")
    product_id: int = Field(..., description="ID of the associated product.")
    user_id: int = Field(...,
                         description="ID of the user who wrote the review.")
    rating: conint(ge=1, le=5) = Field(...,
                                       description="The product rating (1 to 5).")
    content: str = Field(..., max_length=1000,
                         description="The content of the review.")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CartItem(BaseModel):
    cart_id: int = Field(...,
                         description="Unique identifier for the cart entry.")
    product_id: int = Field(..., description="ID of the product.")
    name: str = Field(..., description="Product name.")
    price: int = Field(..., description="Price per unit.")
    image_url: str = Field(..., description="Product image URL.")
    category: str = Field(..., description="Product category.")
    quantity: int = Field(..., description="Quantity in cart.")

    class Config:
        from_attributes = True


class OrderSummary(BaseModel):
    order_id: int = Field(..., description="Unique identifier for the order.")
    total_amount: int = Field(..., description="Total order amount.")
    item_count: int = Field(..., description="Total number of items in order.")
    created_at: datetime = Field(..., description="Timestamp when order was created.")

    class Config:
        from_attributes = True
