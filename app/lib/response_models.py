from pydantic import BaseModel, Field
from typing import List, Optional

from app.lib.base_models import Product, Review, CartItem, OrderSummary


# --- GENERAL RESPONSE STRUCTURES ---
class APIErrorResponse(BaseModel):
    success: bool = Field(
        False, description="Always False for error responses.")
    message: str = Field(
        ..., description="A short, readable error message (e.g., 'Product not found').")
    error_code: Optional[str] = Field(
        None, description="Internal error code (e.g., 'DB_ERROR').")


# --- PRODUCT RESPONSES ---
class ProductListWrapper(BaseModel):
    success: bool = True
    message: str = "Successfully retrieved product list."
    data: List[Product]


class SingleProductWrapper(BaseModel):
    success: bool = True
    message: str = "Successfully retrieved product details."
    data: Product


class ProductInfoWithReviews(BaseModel):
    product: Product
    reviews: List[Review]


class ProductDetailsWrapper(BaseModel):
    success: bool = True
    message: str = "Successfully retrieved product and reviews."
    data: ProductInfoWithReviews


# --- CART RESPONSES ---
class NewCartItem(BaseModel):
    cart_id: Optional[int] = Field(
        None, description="Unique identifier for the cart entry.")
    product_id: int = Field(...,
                            description="ID of the product to add to cart/added to cart.")
    quantity: int = Field(...,
                          description="Quantity of the product to add/in cart.")

    class Config:
        from_attributes = True


class NewCartItemWrapper(BaseModel):
    success: bool = True
    message: str = "Successfully added item to cart."
    data: NewCartItem


class CartListWrapper(BaseModel):
    success: bool = True
    message: str = "Successfully retrieved cart items."
    data: List[CartItem] = []


# --- REVIEW RESPONSES ---
class ReviewResponse(BaseModel):
    id: int = Field(..., description="Unique review identifier.")
    title: str = Field(..., max_length=200, description="Title of the review")
    rating: int = Field(..., ge=1, le=5, description="Rating between 1 and 5.")
    content: str = Field(..., max_length=1000,
                         description="Content of the review.")

    class Config:
        from_attributes = True


class ReviewResponseWrapper(BaseModel):
    succcess: bool = True
    message: str = "Successfully added new review."
    data: ReviewResponse


# --- CHECKOUT RESPONSES ---
class CheckoutResponse(BaseModel):
    success: bool = True
    message: str = "Order placed successfully."
    data: OrderSummary
