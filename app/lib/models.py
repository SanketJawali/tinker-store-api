from sqlalchemy import Integer, String, ForeignKey, Text, DateTime, func
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from typing import List
from datetime import datetime

Base = declarative_base()


class UserDB(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    def __repr__(self):
        return f"UserDB(id={self.id!r}, name={self.name!r})"


class ProductDB(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    price: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), index=True)
    stock: Mapped[int] = mapped_column(Integer)
    image_url: Mapped[str] = mapped_column(String(255))

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Unidirectional relationship: Product knows its owner, but User doesn't list products.
    owner: Mapped["UserDB"] = relationship()

    def __repr__(self):
        return (f"ProductDB(id={self.id!r}, name={self.name!r}, "
                f"owner_id={self.owner_id!r}, stock={self.stock!r})")


class ReviewDB(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Foreign Keys with Indexing
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    rating: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)

    # Timestamps with automatic database defaults
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships (defining the link back to User and Product)
    # user: Mapped["UserDB"] = relationship(back_populates="reviews")
    # product: Mapped["ProductDB"] = relationship(back_populates="reviews")

    def __repr__(self):
        return f"ReviewDB(id={self.id!r}, rating={self.rating!r}, product_id={self.product_id!r})"


class CartDB(Base):
    __tablename__ = "cart"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # ForeignKey with index
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), index=True)

    quantity: Mapped[int] = mapped_column(Integer)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships to access the related objects directly
    user: Mapped["UserDB"] = relationship()
    product: Mapped["ProductDB"] = relationship()

    def __repr__(self):
        return f"CartDB(id = {self.id!r}, user_id={self.user_id!r}, product_id={self.product_id!r}, quantity={self.quantity!r})"


class OrderDB(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # Store snapshot of customer info at time of purchase
    customer_name: Mapped[str] = mapped_column(String(100))
    customer_address: Mapped[str] = mapped_column(Text)
    customer_phone: Mapped[str] = mapped_column(String(20))
    payment_method: Mapped[str] = mapped_column(String(50))

    # In cents/lowest unit as per ProductDB price
    total_amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50), default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Relationships
    items: Mapped[List["OrderItemDB"]] = relationship(
        back_populates="order", cascade="all, delete-orphan")
    user: Mapped["UserDB"] = relationship()

    def __repr__(self):
        return (f"OrderDB(id={self.id!r}, user_id={self.user_id!r}, "
                f"total={self.total_amount!r}, status={self.status!r})")


class OrderItemDB(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), index=True)

    quantity: Mapped[int] = mapped_column(Integer)
    # Snapshot of price
    price_at_purchase: Mapped[int] = mapped_column(Integer)

    order: Mapped["OrderDB"] = relationship(back_populates="items")
    product: Mapped["ProductDB"] = relationship()

    def __repr__(self):
        return (f"OrderItemDB(id={self.id!r}, order_id={self.order_id!r}, "
                f"product_id={self.product_id!r}, quantity={self.quantity!r})")
