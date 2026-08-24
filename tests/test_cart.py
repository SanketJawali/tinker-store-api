"""Tests for cart read/write routes."""


def test_get_cart_requires_auth(client):
    response = client.get("/api/cart")
    assert response.status_code == 401


def test_get_cart_empty_for_new_user(client, auth_headers):
    response = client.get("/api/cart", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == []


def test_add_to_cart_and_list(client, auth_headers, seed_product):
    add = client.post(
        "/api/cart",
        headers=auth_headers,
        json={"product_id": seed_product.id, "quantity": 2},
    )
    assert add.status_code == 200
    assert add.json()["data"]["product_id"] == seed_product.id
    assert add.json()["data"]["quantity"] == 2

    cart = client.get("/api/cart", headers=auth_headers)
    assert cart.status_code == 200
    items = cart.json()["data"]
    assert len(items) == 1
    assert items[0]["product_id"] == seed_product.id
    assert items[0]["quantity"] == 2
    assert items[0]["name"] == seed_product.name


def test_add_to_cart_increments_quantity(client, auth_headers, seed_product):
    client.post(
        "/api/cart",
        headers=auth_headers,
        json={"product_id": seed_product.id, "quantity": 1},
    )
    client.post(
        "/api/cart",
        headers=auth_headers,
        json={"product_id": seed_product.id, "quantity": 3},
    )

    cart = client.get("/api/cart", headers=auth_headers)
    assert cart.json()["data"][0]["quantity"] == 4


def test_add_to_cart_rejects_zero_quantity(client, auth_headers, seed_product):
    response = client.post(
        "/api/cart",
        headers=auth_headers,
        json={"product_id": seed_product.id, "quantity": 0},
    )
    assert response.status_code == 400


def test_add_to_cart_unknown_product(client, auth_headers):
    response = client.post(
        "/api/cart",
        headers=auth_headers,
        json={"product_id": 99999, "quantity": 1},
    )
    assert response.status_code == 404
