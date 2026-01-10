from pydantic import BaseModel, Field
from typing import Optional


# --- REQUEST MODELS ---
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


class ReviewRequest(BaseModel):
    product_id: int = Field(..., description="ID of the associated product.")
    title: str = Field(..., max_length=200, description="Title of the review.")
    rating: int = Field(..., ge=1, le=5, description="Rating between 1 and 5.")
    content: str = Field(..., max_length=1000,
                         description="Content of the review.")


class CheckoutRequest(BaseModel):
    name: str = Field(..., max_length=100, description="Customer full name.")
    address: str = Field(..., description="Shipping address.")
    phone: str = Field(..., max_length=20, description="Contact phone number.")
    payment_method: str = Field(..., max_length=50,
                                description="Payment method (e.g., 'credit_card', 'paypal').")
