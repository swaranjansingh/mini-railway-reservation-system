from fastapi.testclient import TestClient
from sqlmodel import Session
from app.models.user import User


def test_get_current_user_profile(
    client: TestClient, passenger_user: User, passenger_headers: dict
):
    response = client.get("/api/users/me", headers=passenger_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == passenger_user.id
    assert data["email"] == passenger_user.email
    assert data["role"] == "passenger"


def test_update_profile_name(client: TestClient, passenger_headers: dict):
    response = client.patch(
        "/api/users/me",
        headers=passenger_headers,
        json={"name": "Rahul Updated Sharma"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Rahul Updated Sharma"


def test_update_password_success_and_failure(
    client: TestClient, passenger_headers: dict
):
    # Fails with wrong current password
    fail_res = client.patch(
        "/api/users/me",
        headers=passenger_headers,
        json={
            "current_password": "WrongPassword123!",
            "new_password": "NewValidPassword123!",
        },
    )
    assert fail_res.status_code == 400
    assert "verification failed" in fail_res.json()["detail"].lower()

    # Succeeds with correct current password
    succ_res = client.patch(
        "/api/users/me",
        headers=passenger_headers,
        json={
            "current_password": "PassengerPass123!",
            "new_password": "NewValidPassword123!",
        },
    )
    assert succ_res.status_code == 200

    # Reset password back for other tests
    client.patch(
        "/api/users/me",
        headers=passenger_headers,
        json={
            "current_password": "NewValidPassword123!",
            "new_password": "PassengerPass123!",
        },
    )
