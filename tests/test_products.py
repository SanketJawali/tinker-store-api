"""Tests for product list, detail, and create routes."""


PRODUCT_PAYLOAD = {
    "name": "Mechanical Keyboard",
    "price": 7999,
    "description": "Tactile switches, RGB backlight",
    "category": "electronics",
    "stock": 5,
    "image_url": "https://example.com/keyboard.jpg",
}


def test_list_products_empty(client):
    response = client.get("/api/product")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == []


def test_list_products_returns_seeded_item(client, seed_product):
    response = client.get("/api/product")
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["name"] == seed_product.name
    assert body["data"][0]["id"] == seed_product.id


def test_list_products_search_filter(client, seed_product):
    hit = client.get("/api/product", params={"q": "mouse"})
    assert hit.status_code == 200
    assert len(hit.json()["data"]) == 1

    miss = client.get("/api/product", params={"q": "unicorn"})
    assert miss.status_code == 200
    assert miss.json()["data"] == []


def test_list_products_uses_cache(client, seed_product, fake_redis, db_session):
    first = client.get("/api/product", params={"page": 1, "limit": 20})
    assert first.status_code == 200
    assert "products:all:page:1:limit:20" in fake_redis._store

    # Mutate DB after cache fill; cached response should still be returned.
    seed_product.name = "Changed Name"
    db_session.commit()

    second = client.get("/api/product", params={"page": 1, "limit": 20})
    assert second.status_code == 200
    assert second.json()["data"][0]["name"] == "Wireless Mouse"


def test_get_product_details(client, seed_product):
    response = client.get(f"/api/product/{seed_product.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["product"]["id"] == seed_product.id
    assert body["data"]["reviews"] == []


def test_get_product_not_found(client):
    response = client.get("/api/product/99999")
    assert response.status_code == 404


def test_create_product_requires_auth(client):
    response = client.post("/api/product", json=PRODUCT_PAYLOAD)
    assert response.status_code == 401


def test_create_product_success(client, auth_headers, db_session):
    response = client.post(
        "/api/product", json=PRODUCT_PAYLOAD, headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["name"] == PRODUCT_PAYLOAD["name"]
    assert body["data"]["price"] == PRODUCT_PAYLOAD["price"]
    assert body["data"]["owner_id"] is not None

    listed = client.get("/api/product")
    assert len(listed.json()["data"]) == 1


def test_create_product_invalidates_list_cache(
    client, auth_headers, seed_product, fake_redis
):
    client.get("/api/product")
    assert fake_redis.keys("products:*")

    response = client.post(
        "/api/product", json=PRODUCT_PAYLOAD, headers=auth_headers
    )
    assert response.status_code == 201
    assert fake_redis.keys("products:*") == []
