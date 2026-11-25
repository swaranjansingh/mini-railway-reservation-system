from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.user import User, UserRole
from app.models.password_reset import PasswordResetToken
from app.security.password import hash_password, hash_token


def test_forgot_password_generic_response(client: TestClient):
    # Non-existent user
    res = client.post(
        "/api/auth/forgot-password",
        json={"email": "nonexistent.random@example.com"},
    )
    assert res.status_code == 200
    assert "dispatched" in res.json()["message"].lower()
    assert res.json().get("dev_reset_token") is None


def test_password_reset_flow(client: TestClient, session: Session):
    email = "reset.user@example.com"
    user = User(
        name="Reset Test User",
        email=email,
        hashed_password=hash_password("OldPassword123!"),
        role=UserRole.PASSENGER,
        is_active=True,
    )
    session.add(user)
    session.commit()

    # Step 1: Request reset
    forgot_res = client.post(
        "/api/auth/forgot-password",
        json={"email": email},
    )
    assert forgot_res.status_code == 200
    token = forgot_res.json().get("dev_reset_token")
    assert token is not None

    # Step 2: Try with invalid token
    invalid_res = client.post(
        "/api/auth/reset-password",
        json={"token": "InvalidToken12345", "new_password": "BrandNewPassword123!"},
    )
    assert invalid_res.status_code == 400
    assert "invalid, expired, or previously used" in invalid_res.json()["detail"].lower()

    # Step 3: Successfully reset with valid token
    success_res = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "BrandNewPassword123!"},
    )
    assert success_res.status_code == 200
    assert "successfully reset" in success_res.json()["message"].lower()

    # Step 4: Token cannot be reused (single-use constraint)
    reused_res = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "AnotherNewPassword123!"},
    )
    assert reused_res.status_code == 400
    assert "already been used" in reused_res.json()["detail"].lower()

    # Step 5: Verify login with new password succeeds and old password fails
    fail_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "OldPassword123!"},
    )
    assert fail_login.status_code == 401

    succ_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "BrandNewPassword123!"},
    )
    assert succ_login.status_code == 200
    assert "access_token" in succ_login.json()


def test_expired_password_reset_token(client: TestClient, session: Session):
    email = "expired.token.user@example.com"
    user = User(
        name="Expired User",
        email=email,
        hashed_password=hash_password("Pass12345!"),
        role=UserRole.PASSENGER,
        is_active=True,
    )
    session.add(user)
    session.commit()

    raw_token = "ExpiredTokenSimulation123456789"
    token_hash = hash_token(raw_token)
    past_time = datetime.now(timezone.utc) - timedelta(minutes=20)

    token_record = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=past_time,
        created_at=past_time - timedelta(minutes=10),
    )
    session.add(token_record)
    session.commit()

    res = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "NewSecretPass123!"},
    )
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower()
