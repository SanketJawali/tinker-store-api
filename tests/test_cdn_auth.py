"""Tests for ImageKit CDN auth parameters."""


def test_cdn_auth_requires_auth(client):
    response = client.get("/api/cdn-auth")
    assert response.status_code == 401


def test_cdn_auth_returns_parameters(client, auth_headers):
    response = client.get("/api/cdn-auth", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["token"] == "ik_test_token"
    assert body["signature"] == "ik_test_signature"
    assert "expire" in body
