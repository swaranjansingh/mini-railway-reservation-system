from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.user import User, UserRole
from app.security.password import hash_password
from app.security.jwt import create_access_token


def test_register_success(client: TestClient):
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Amit Kumar",
            "email": "amit.kumar@example.com",
            "password": "Password123!",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "amit.kumar@example.com"
    assert data["role"] == "passenger"
    assert data["is_active"] is True
    assert "hashed_password" not in data


def test_register_duplicate_email(client: TestClient):
    payload = {
        "name": "Amit Duplicate",
        "email": "amit.duplicate@example.com",
        "password": "Password123!",
    }
    res1 = client.post("/api/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/auth/register", json=payload)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"].lower()


def test_login_success(client: TestClient, session: Session):
    email = "login.test@example.com"
    user = User(
        name="Login Test",
        email=email,
        hashed_password=hash_password("ValidPassword123!"),
        role=UserRole.PASSENGER,
        is_active=True,
    )
    session.add(user)
    session.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "ValidPassword123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "passenger"


def test_login_invalid_password(client: TestClient, session: Session):
    response = client.post(
        "/api/auth/login",
        json={"email": "login.test@example.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()


def test_login_inactive_account(client: TestClient, session: Session):
    email = "inactive.user@example.com"
    user = User(
        name="Inactive User",
        email=email,
        hashed_password=hash_password("ValidPass123!"),
        role=UserRole.PASSENGER,
        is_active=False,
    )
    session.add(user)
    session.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "ValidPass123!"},
    )
    assert response.status_code == 401
    assert "deactivated" in response.json()["detail"].lower()


def test_missing_jwt(client: TestClient):
    response = client.get("/api/users/me")
    assert response.status_code == 401
    assert "credentials were not provided" in response.json()["detail"].lower()


def test_invalid_jwt(client: TestClient):
    response = client.get(
        "/api/users/me",
        headers={"Authorization": "Bearer invalid.token.structure"},
    )
    assert response.status_code == 401
    assert "invalid or expired" in response.json()["detail"].lower()


def test_expired_jwt(client: TestClient, passenger_user: User):
    token_dict = create_access_token(
        user_id=passenger_user.id,
        email=passenger_user.email,
        role=passenger_user.role.value,
        expires_delta=timedelta(seconds=-10),
    )
    response = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {token_dict['token']}"},
    )
    assert response.status_code == 401
    assert "invalid or expired" in response.json()["detail"].lower()


def test_logout_and_revocation(client: TestClient, session: Session):
    email = "logout.test@example.com"
    user = User(
        name="Logout Test",
        email=email,
        hashed_password=hash_password("Pass123456!"),
        role=UserRole.PASSENGER,
        is_active=True,
    )
    session.add(user)
    session.commit()

    login_res = client.post(
        "/api/auth/login",
        json={"email": email, "password": "Pass123456!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify protected route works before logout
    profile_res = client.get("/api/users/me", headers=headers)
    assert profile_res.status_code == 200

    # Perform logout
    logout_res = client.post("/api/auth/logout", headers=headers)
    assert logout_res.status_code == 200
    assert "revoked" in logout_res.json()["message"].lower()

    # Attempt to use revoked token
    revoked_res = client.get("/api/users/me", headers=headers)
    assert revoked_res.status_code == 401
    assert "revoked" in revoked_res.json()["detail"].lower()


def test_passenger_accessing_admin_forbidden(
    client: TestClient, passenger_headers: dict
):
    response = client.post(
        "/api/admin/stations",
        headers=passenger_headers,
        json={"station_code": "TEST", "name": "Test Station", "city": "City"},
    )
    assert response.status_code == 403
    assert "administrative privileges required" in response.json()["detail"].lower()
