from datetime import date, timedelta
from fastapi.testclient import TestClient
from app.models.train import Train


def test_root_and_health_endpoints(client: TestClient):
    root_res = client.get("/")
    assert root_res.status_code == 200
    root_data = root_res.json()
    assert "Mini Railway Reservation System" in root_data["name"]
    assert root_data["status"] == "online"
    assert root_data["documentation"] == "/docs"

    health_res = client.get("/health")
    assert health_res.status_code == 200
    health_data = health_res.json()
    assert health_data["status"] == "healthy"
    assert health_data["database"] == "connected"


def test_stations_public_endpoints(client: TestClient, sample_stations: dict):
    # List stations
    list_res = client.get("/api/stations")
    assert list_res.status_code == 200
    stations = list_res.json()
    assert len(stations) >= 5

    # Get station by ID
    ndls_id = sample_stations["NDLS"].id
    get_res = client.get(f"/api/stations/{ndls_id}")
    assert get_res.status_code == 200
    assert get_res.json()["station_code"] == "NDLS"

    # Non-existent station
    fail_res = client.get("/api/stations/999999")
    assert fail_res.status_code == 404


def test_train_details_endpoint(client: TestClient, sample_train: Train):
    res = client.get(f"/api/trains/{sample_train.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["train_number"] == "12004"
    assert len(data["stops"]) == 5


def test_admin_list_trains(client: TestClient, admin_headers: dict, sample_train: Train):
    res = client.get("/api/admin/trains", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert any(t["train_number"] == "12004" for t in data)


def test_user_and_booking_history_endpoints(
    client: TestClient,
    passenger_headers: dict,
    sample_train: Train,
):
    journey_date = str(date.today() + timedelta(days=20))

    # Book a ticket
    book_res = client.post(
        "/api/bookings",
        headers=passenger_headers,
        json={
            "train_id": sample_train.id,
            "journey_date": journey_date,
            "source_station_code": "NDLS",
            "destination_station_code": "GZB",
        },
    )
    assert book_res.status_code == 201
    pnr = book_res.json()["pnr"]

    # View my bookings via /api/bookings/me
    my_bookings_res = client.get("/api/bookings/me", headers=passenger_headers)
    assert my_bookings_res.status_code == 200
    pnrs = [b["pnr"] for b in my_bookings_res.json()]
    assert pnr in pnrs

    # View my bookings via /api/users/me/bookings
    user_bookings_res = client.get("/api/users/me/bookings", headers=passenger_headers)
    assert user_bookings_res.status_code == 200
    user_pnrs = [b["pnr"] for b in user_bookings_res.json()]
    assert pnr in user_pnrs

    # Get single booking by PNR
    single_res = client.get(f"/api/bookings/{pnr}", headers=passenger_headers)
    assert single_res.status_code == 200
    assert single_res.json()["pnr"] == pnr
    assert single_res.json()["fare"] == 65.0
