from pydantic import BaseModel, EmailStr, Field, conint
from typing import Optional
from datetime import datetime


class User(BaseModel):
    id: int = Field(..., description="Unique user identifier.")
    name: str = Field(..., max_length=100, description="User's full name.")
    email: EmailStr = Field(..., max_length=100,
                            description="Unique user email address.")

    class Config:
        from_attributes = True


class ProductRequest(BaseModel):
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
    item_id: int = Field(..., description="ID of the associated product.")
    user_id: int = Field(...,
                         description="ID of the user who wrote the review.")
    # Rating constrained to be between 1 and 5
    rating: conint(ge=1, le=5) = Field(...,
                                       description="The product rating (1 to 5).")
    # The actual review text. We add a maximum length.
    review_text: str = Field(..., max_length=1000,
                             description="The content of the review.")
    # Timestamps for tracking
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
