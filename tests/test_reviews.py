"""Tests for review creation."""


def test_post_review_requires_auth(client, seed_product):
    response = client.post(
        "/api/review",
        json={
            "product_id": seed_product.id,
            "title": "Great",
            "rating": 5,
            "content": "Works well",
        },
    )
    assert response.status_code == 401


def test_post_review_success(client, auth_headers, seed_product, fake_redis):
    # Prime product detail cache so we can assert invalidation.
    client.get(f"/api/product/{seed_product.id}")
    assert fake_redis.get(f"product:{seed_product.id}:details") is not None

    response = client.post(
        "/api/review",
        headers=auth_headers,
        json={
            "product_id": seed_product.id,
            "title": "Solid build",
            "rating": 4,
            "content": "Comfortable for long sessions.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["title"] == "Solid build"
    assert body["data"]["rating"] == 4
    assert body["data"]["id"] is not None
    assert fake_redis.get(f"product:{seed_product.id}:details") is None

    details = client.get(f"/api/product/{seed_product.id}")
    reviews = details.json()["data"]["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["rating"] == 4


def test_post_review_unknown_product(client, auth_headers):
    response = client.post(
        "/api/review",
        headers=auth_headers,
        json={
            "product_id": 99999,
            "title": "Nope",
            "rating": 1,
            "content": "Missing product",
        },
    )
    assert response.status_code == 404


def test_post_review_invalid_rating(client, auth_headers, seed_product):
    response = client.post(
        "/api/review",
        headers=auth_headers,
        json={
            "product_id": seed_product.id,
            "title": "Bad rating",
            "rating": 6,
            "content": "Out of range",
        },
    )
    assert response.status_code == 422
