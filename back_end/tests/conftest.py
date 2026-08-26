import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import create_app
from app.database import Base, get_db
from app.models import User
from app.services.auth_service import AuthService


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def admin(db_session):
    user = User(
        username="admin",
        full_name="Administrator",
        password_hash=AuthService().hash_password("password123"),
        role="admin",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def client(db_session, admin):
    app = create_app()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


@pytest.fixture()
def logged_in_client(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    assert response.status_code == 200
    return client
