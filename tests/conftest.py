"""
Shared fixtures for isolated API tests.

Real Turso, Redis, Clerk, ImageKit, and email are never contacted.
"""
from __future__ import annotations

import os
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Force test configuration before importing the app so Settings / auth
# never pick up production connection targets from the process environment.
_TEST_ENV = {
    "TURSO_DATABASE_URL": "libsql://test.invalid",
    "TURSO_AUTH_TOKEN": "test-auth-token",
    "IMAGE_KIT_PRIVATE_KEY": "test_private_key",
    "IMAGE_KIT_PUBLIC_KEY": "test_public_key",
    "IMAGE_KIT_URL": "https://ik.imagekit.io/test",
    "CLERK_SECRET_KEY": "sk_test_dummy",
    "CLERK_ISSUER": "https://clerk.test.invalid",
    "GROQ_API_KEY": "gsk_test_dummy",
    "REDIS_URL": "redis://localhost:6379/15",
    "SMTP_FROM_EMAIL": "orders@example.com",
    "FRONTEND_URL": "http://localhost:3000",
    "ADMINS": "admin@example.com",
}
for _key, _value in _TEST_ENV.items():
    os.environ[_key] = _value


class FakeRedis:
    """Minimal in-memory Redis stand-in used by product/cart cache paths."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: str, ex: int | None = None):
        self._store[key] = value
        return True

    def keys(self, pattern: str):
        # Only the patterns used by the app are supported (prefix + "*").
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return [key for key in self._store if key.startswith(prefix)]
        return [key for key in self._store if key == pattern]

    def delete(self, *keys: str):
        removed = 0
        for key in keys:
            if key in self._store:
                del self._store[key]
                removed += 1
        return removed

    def ping(self):
        return True

    def close(self):
        return None


@pytest.fixture()
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.lib.models import Base

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def auth_user() -> dict:
    return {
        "email": "shopper@example.com",
        "name": "Test Shopper",
        "sub": "user_test_123",
    }


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


@pytest.fixture()
def email_mock() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def client(
    db_session: Session,
    fake_redis: FakeRedis,
    auth_user: dict,
    email_mock: MagicMock,
) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_redis():
        return fake_redis

    def fake_validate_token(_token: str):
        return auth_user

    with (
        patch("app.main.Redis.from_url", return_value=fake_redis),
        patch("app.main.Base.metadata.create_all"),
        patch("app.lib.auth.validate_token_logic", side_effect=fake_validate_token),
        patch(
            "app.main.imagekit.helper.get_authentication_parameters",
            return_value={
                "token": "ik_test_token",
                "expire": 9999999999,
                "signature": "ik_test_signature",
            },
        ),
        patch("app.main.send_order_confirmation_email", email_mock),
    ):
        from app.main import app, get_db, get_redis_client

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_redis_client] = override_get_redis

        with TestClient(app) as test_client:
            yield test_client

        app.dependency_overrides.clear()


@pytest.fixture()
def seed_product(db_session: Session):
    """Insert an owner + product used by cart / review / detail tests."""
    from app.lib.models import ProductDB, UserDB

    owner = UserDB(name="Owner", email="owner@example.com")
    db_session.add(owner)
    db_session.flush()

    product = ProductDB(
        name="Wireless Mouse",
        price=2500,
        description="Ergonomic wireless mouse",
        category="electronics",
        stock=10,
        image_url="https://example.com/mouse.jpg",
        owner_id=owner.id,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product
