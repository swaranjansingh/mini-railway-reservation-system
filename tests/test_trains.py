from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session
from app.models.train import Train


def test_search_trains_valid_route(
    client: TestClient, sample_train: Train, sample_stations: dict
):
    journey_date = str(date.today() + timedelta(days=2))
    response = client.get(
        "/api/trains/search",
        params={
            "source_station_code": "NDLS",
            "destination_station_code": "CNB",
            "journey_date": journey_date,
        },
    )
    assert response.status_code == 200
    trains = response.json()
    assert len(trains) >= 1

    match = next(t for t in trains if t["train_number"] == "12004")
    assert match["train_name"] == "Lucknow Shatabdi"
    assert match["fare"] == 650.0  # CNB fare (650) - NDLS fare (0)
    assert match["departure_time"] == "06:10"
    assert match["arrival_time"] == "11:20"
    assert match["available_seats"] == 5


def test_search_intermediate_segment_fare(
    client: TestClient, sample_train: Train
):
    # Segment: GZB (fare 65) to CNB (fare 650) -> segment fare = 650 - 65 = 585
    journey_date = str(date.today() + timedelta(days=3))
    response = client.get(
        "/api/trains/search",
        params={
            "source_station_code": "GZB",
            "destination_station_code": "CNB",
            "journey_date": journey_date,
        },
    )
    assert response.status_code == 200
    trains = response.json()
    match = next(t for t in trains if t["train_number"] == "12004")
    assert match["fare"] == 585.0
    assert match["departure_time"] == "06:50"
    assert match["arrival_time"] == "11:20"


def test_search_same_source_and_destination_rejected(client: TestClient):
    journey_date = str(date.today() + timedelta(days=1))
    response = client.get(
        "/api/trains/search",
        params={
            "source_station_code": "NDLS",
            "destination_station_code": "NDLS",
            "journey_date": journey_date,
        },
    )
    assert response.status_code == 400
    assert "cannot be identical" in response.json()["detail"].lower()


def test_search_nonexistent_station(client: TestClient):
    journey_date = str(date.today() + timedelta(days=1))
    response = client.get(
        "/api/trains/search",
        params={
            "source_station_code": "XYZ99",
            "destination_station_code": "NDLS",
            "journey_date": journey_date,
        },
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_search_reverse_direction_excluded(
    client: TestClient, sample_train: Train
):
    # Train goes NDLS -> CNB. Searching CNB -> NDLS should return 0 matching trains for this train.
    journey_date = str(date.today() + timedelta(days=1))
    response = client.get(
        "/api/trains/search",
        params={
            "source_station_code": "CNB",
            "destination_station_code": "NDLS",
            "journey_date": journey_date,
        },
    )
    assert response.status_code == 200
    # No train goes in reverse direction
    trains = [t for t in response.json() if t["train_number"] == "12004"]
    assert len(trains) == 0


def test_train_availability_endpoint(
    client: TestClient, sample_train: Train
):
    journey_date = str(date.today() + timedelta(days=5))
    response = client.get(
        f"/api/trains/{sample_train.id}/availability",
        params={
            "source_station_code": "NDLS",
            "destination_station_code": "LKO",
            "journey_date": journey_date,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_seats"] == 5
    assert data["booked_seats"] == 0
    assert data["available_seats"] == 5
