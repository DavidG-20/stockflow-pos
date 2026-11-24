"""Shared pytest fixtures backed by an isolated in-memory SQLite database."""

from collections.abc import Generator

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from stockflow_pos.core.database import Base, get_db
from stockflow_pos.core.security import login_rate_limiter
from stockflow_pos.core.seed import seed_initial_data
from stockflow_pos.main import app


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Provide a TestClient with a fresh, seeded in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as seed_db:
        seed_initial_data(seed_db)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    login_rate_limiter.reset()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    login_rate_limiter.reset()
    Base.metadata.drop_all(bind=engine)
