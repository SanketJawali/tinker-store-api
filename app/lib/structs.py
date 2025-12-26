from pydantic import BaseModel, Field, conint, EmailStr
from typing import List, Optional
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
    item_id: int = Field(..., description="ID of the associated product.")
    user_id: int = Field(...,
                         description="ID of the user who wrote the review.")
    rating: conint(ge=1, le=5) = Field(...,
                                       description="The product rating (1 to 5).")
    review_text: str = Field(..., max_length=1000,
                             description="The content of the review.")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- API REQUEST MODELS ---
class ProductRequest(BaseModel):
    name: str = Field(..., max_length=100, description="Product name.")
    price: int = Field(..., gt=0, description="Price.")
    description: str = Field(..., description="Detailed product description.")
    category: str = Field(..., max_length=50, description="Product category.")
    stock: int = Field(..., ge=0, description="Current stock quantity.")
    image_url: str = Field(..., max_length=255,
                           description="URL of the product image.")

    class Config:
        from_attributes = True


# --- GENERAL RESPONSE STRUCTURES ---
# 1. Standard Error Response Structure
class APIErrorResponse(BaseModel):
    success: bool = Field(
        False, description="Always False for error responses.")
    message: str = Field(
        ..., description="A short, readable error message (e.g., 'Product not found').")
    error_code: Optional[str] = Field(
        None, description="Internal error code (e.g., 'DB_ERROR').")


# 2. Wrapper for List Responses (e.g., GET /api/product)
class ProductListWrapper(BaseModel):
    success: bool = True
    message: str = "Successfully retrieved product list."
    data: List[Product]


# 3. Wrapper for Single Item Responses (e.g., POST /api/product, GET /api/product/1)
class SingleProductWrapper(BaseModel):
    success: bool = True
    message: str = "Successfully retrieved product details."
    data: Product


# 4. Wrapper for Product Details with Reviews (GET /api/product/{id})
class ProductInfoWithReviews(BaseModel):
    product: Product
    reviews: List[Review]


class ProductDetailsWrapper(BaseModel):
    success: bool = True
    message: str = "Successfully retrieved product and reviews."
    data: ProductInfoWithReviews
