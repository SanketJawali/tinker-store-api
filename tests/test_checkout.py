"""Tests for checkout flow."""


CHECKOUT_PAYLOAD = {
    "name": "Test Shopper",
    "address": "123 Test Street",
    "phone": "555-0100",
    "payment_method": "credit_card",
}


def _add_to_cart(client, auth_headers, product_id: int, quantity: int = 2):
    response = client.post(
        "/api/cart",
        headers=auth_headers,
        json={"product_id": product_id, "quantity": quantity},
    )
    assert response.status_code == 200


def test_checkout_requires_auth(client):
    response = client.post("/api/checkout", json=CHECKOUT_PAYLOAD)
    assert response.status_code == 401


def test_checkout_empty_cart(client, auth_headers, db_session, auth_user):
    # Ensure the authenticated user exists locally so checkout reaches empty-cart logic.
    from app.lib.models import UserDB

    db_session.add(
        UserDB(name=auth_user["name"], email=auth_user["email"])
    )
    db_session.commit()

    response = client.post(
        "/api/checkout", headers=auth_headers, json=CHECKOUT_PAYLOAD
    )
    assert response.status_code == 400


def test_checkout_user_not_found(client, auth_headers):
    response = client.post(
        "/api/checkout", headers=auth_headers, json=CHECKOUT_PAYLOAD
    )
    assert response.status_code == 404


def test_checkout_success_clears_cart_and_reduces_stock(
    client, auth_headers, seed_product, db_session
):
    _add_to_cart(client, auth_headers, seed_product.id, quantity=3)

    response = client.post(
        "/api/checkout", headers=auth_headers, json=CHECKOUT_PAYLOAD
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["order_id"] is not None
    assert body["data"]["item_count"] == 3
    assert body["data"]["total_amount"] == seed_product.price * 3

    cart = client.get("/api/cart", headers=auth_headers)
    assert cart.json()["data"] == []

    db_session.refresh(seed_product)
    assert seed_product.stock == 7


def test_checkout_insufficient_stock(
    client, auth_headers, seed_product, db_session
):
    seed_product.stock = 1
    db_session.commit()

    _add_to_cart(client, auth_headers, seed_product.id, quantity=5)

    response = client.post(
        "/api/checkout", headers=auth_headers, json=CHECKOUT_PAYLOAD
    )
    assert response.status_code == 400
