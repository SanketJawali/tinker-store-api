"""
End-to-end checkout journey via the public API surface.

Flow: create product → add to cart → checkout → verify cart/stock/email side effects.
Still fully isolated (in-memory DB + mocked Redis/auth/email).
"""

from sqlalchemy import select

from app.lib.models import OrderDB, OrderItemDB


def test_e2e_checkout_happy_path(
    client, auth_headers, auth_user, email_mock, db_session
):
    # 1. Seller/shopper creates a product
    create = client.post(
        "/api/product",
        headers=auth_headers,
        json={
            "name": "USB-C Hub",
            "price": 4500,
            "description": "7-in-1 multiport adapter",
            "category": "electronics",
            "stock": 8,
            "image_url": "https://example.com/hub.jpg",
        },
    )
    assert create.status_code == 201
    product = create.json()["data"]
    product_id = product["id"]
    unit_price = product["price"]

    # 2. Product appears in catalog
    catalog = client.get("/api/product")
    assert catalog.status_code == 200
    assert any(item["id"] == product_id for item in catalog.json()["data"])

    # 3. Add two units to cart
    add_cart = client.post(
        "/api/cart",
        headers=auth_headers,
        json={"product_id": product_id, "quantity": 2},
    )
    assert add_cart.status_code == 200

    cart_before = client.get("/api/cart", headers=auth_headers)
    assert cart_before.status_code == 200
    cart_items = cart_before.json()["data"]
    assert len(cart_items) == 1
    assert cart_items[0]["product_id"] == product_id
    assert cart_items[0]["quantity"] == 2

    # 4. Checkout
    checkout = client.post(
        "/api/checkout",
        headers=auth_headers,
        json={
            "name": auth_user["name"],
            "address": "42 Integration Ave",
            "phone": "555-0199",
            "payment_method": "credit_card",
        },
    )
    assert checkout.status_code == 200
    order = checkout.json()["data"]
    assert order["order_id"] is not None
    assert order["item_count"] == 2
    assert order["total_amount"] == unit_price * 2
    assert order["created_at"] is not None

    # 5. Cart is cleared
    cart_after = client.get("/api/cart", headers=auth_headers)
    assert cart_after.status_code == 200
    assert cart_after.json()["data"] == []

    # 6. Stock decreased (visible via product detail API)
    details = client.get(f"/api/product/{product_id}")
    assert details.status_code == 200
    assert details.json()["data"]["product"]["stock"] == 6

    # 7. Order + line items persisted
    db_order = db_session.get(OrderDB, order["order_id"])
    assert db_order is not None
    assert db_order.customer_name == auth_user["name"]
    assert db_order.customer_address == "42 Integration Ave"
    assert db_order.payment_method == "credit_card"
    assert db_order.status == "completed"
    assert db_order.total_amount == unit_price * 2

    line_items = db_session.scalars(
        select(OrderItemDB).where(OrderItemDB.order_id == db_order.id)
    ).all()
    assert len(line_items) == 1
    assert line_items[0].product_id == product_id
    assert line_items[0].quantity == 2
    assert line_items[0].price_at_purchase == unit_price

    # 8. Confirmation email queued with expected args
    email_mock.assert_called_once()
    email_kwargs = email_mock.call_args.kwargs
    assert email_kwargs["to_email"] == auth_user["email"]
    assert email_kwargs["customer_name"] == auth_user["name"]
    assert email_kwargs["order_id"] == order["order_id"]
    assert email_kwargs["total_amount"] == unit_price * 2
    assert email_kwargs["item_count"] == 2
    assert email_kwargs["order_items"] == [
        {"name": "USB-C Hub", "quantity": 2, "price": unit_price}
    ]

    # 9. Second checkout with empty cart fails
    second = client.post(
        "/api/checkout",
        headers=auth_headers,
        json={
            "name": auth_user["name"],
            "address": "42 Integration Ave",
            "phone": "555-0199",
            "payment_method": "credit_card",
        },
    )
    assert second.status_code == 400
