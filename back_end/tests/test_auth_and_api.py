from app.models import User
from app.services.auth_service import AuthService


def test_password_hash_is_not_plaintext():
    service = AuthService()
    digest = service.hash_password("password123")
    assert digest != "password123"
    assert service.verify_password("password123", digest)


def test_login_sets_http_only_cookies_and_me_works(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    assert response.status_code == 200
    assert "entok_access" in response.cookies
    assert "HttpOnly" in response.headers["set-cookie"]
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["role"] == "admin"


def test_operator_cannot_manage_users(client, db_session):
    db_session.add(User(username="operator", full_name="Operator", password_hash=AuthService().hash_password("password123"), role="operator"))
    db_session.commit()
    client.post("/api/auth/login", json={"username": "operator", "password": "password123"})
    response = client.get("/api/users")
    assert response.status_code == 403


def test_admin_can_create_and_disable_operator(logged_in_client):
    created = logged_in_client.post("/api/users", json={"username": "operator1", "full_name": "Operator Satu", "password": "password123", "role": "operator"})
    assert created.status_code == 201
    user_id = created.json()["data"]["id"]
    updated = logged_in_client.patch(f"/api/users/{user_id}", json={"is_active": False})
    assert updated.status_code == 200
    assert updated.json()["data"]["is_active"] is False


def test_media_path_traversal_is_rejected(logged_in_client):
    response = logged_in_client.get("/api/media/uploads/..%2F.env")
    assert response.status_code == 404
