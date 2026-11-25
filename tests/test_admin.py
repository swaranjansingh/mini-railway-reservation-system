from fastapi.testclient import TestClient
from sqlmodel import Session


def test_admin_create_station(client: TestClient, admin_headers: dict):
    response = client.post(
        "/api/admin/stations",
        headers=admin_headers,
        json={"station_code": "MTC", "name": "Meerut City", "city": "Meerut"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["station_code"] == "MTC"
    assert data["name"] == "Meerut City"


def test_admin_reject_duplicate_station(
    client: TestClient, admin_headers: dict, sample_stations: dict
):
    # Try creating NDLS again (already created in sample_stations)
    response = client.post(
        "/api/admin/stations",
        headers=admin_headers,
        json={"station_code": "NDLS", "name": "New Delhi Duplicate", "city": "Delhi"},
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_admin_create_and_update_train(
    client: TestClient, admin_headers: dict, sample_stations: dict
):
    train_payload = {
        "train_number": "12006",
        "name": "Kalka Shatabdi",
        "total_seats": 60,
        "stops": [
            {
                "station_id": sample_stations["NDLS"].id,
                "stop_order": 1,
                "arrival_time": None,
                "departure_time": "17:15",
                "fare_from_origin": 0.0,
            },
            {
                "station_id": sample_stations["GZB"].id,
                "stop_order": 2,
                "arrival_time": "17:50",
                "departure_time": "17:52",
                "fare_from_origin": 75.0,
            },
        ],
    }
    create_res = client.post(
        "/api/admin/trains",
        headers=admin_headers,
        json=train_payload,
    )
    assert create_res.status_code == 201
    train_data = create_res.json()
    assert train_data["train_number"] == "12006"
    assert len(train_data["stops"]) == 2

    # Update capacity
    update_res = client.patch(
        f"/api/admin/trains/{train_data['id']}",
        headers=admin_headers,
        json={"total_seats": 75},
    )
    assert update_res.status_code == 200
    assert update_res.json()["total_seats"] == 75


def test_admin_reject_invalid_train_capacity(
    client: TestClient, admin_headers: dict
):
    res = client.post(
        "/api/admin/trains",
        headers=admin_headers,
        json={
            "train_number": "99999",
            "name": "Invalid Train",
            "total_seats": 0,
        },
    )
    assert res.status_code == 422 or res.status_code == 400


def test_admin_deactivate_train(
    client: TestClient, admin_headers: dict, sample_stations: dict
):
    # Create a temporary train
    res = client.post(
        "/api/admin/trains",
        headers=admin_headers,
        json={"train_number": "12999", "name": "Temp Express", "total_seats": 20},
    )
    assert res.status_code == 201
    train_id = res.json()["id"]

    deact_res = client.patch(
        f"/api/admin/trains/{train_id}/deactivate",
        headers=admin_headers,
    )
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False


def test_passenger_cannot_mutate_admin_trains(
    client: TestClient, passenger_headers: dict
):
    res = client.post(
        "/api/admin/trains",
        headers=passenger_headers,
        json={"train_number": "88888", "name": "Unauthorized", "total_seats": 50},
    )
    assert res.status_code == 403
