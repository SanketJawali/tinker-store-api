from pydantic import BaseModel


class User(BaseModel):
    id: int
    name: str
    email: str
    cart: list[int]


class ProductRequest(BaseModel):
    name: str
    price: int
    description: str
    category: str
    stock: int
    owner_id: int
    image_url: str


class Product(BaseModel):
    id: int
    name: str
    price: int
    description: str
    category: str
    stock: int
    owner_id: int
    image_url: str


class Review(BaseModel):
    id: int
    item_id: int
    user_id: int
    rating: int
    review: str
