from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session
from app.models.train import Train
from app.models.booking import Booking, BookingStatus
from app.services.booking_service import get_railway_operating_date


def test_booking_success_and_pnr_generation(
    client: TestClient,
    passenger_headers: dict,
    sample_train: Train,
):
    journey_date = str(get_railway_operating_date() + timedelta(days=7))
    payload = {
        "train_id": sample_train.id,
        "journey_date": journey_date,
        "source_station_code": "NDLS",
        "destination_station_code": "CNB",
    }
    response = client.post("/api/bookings", headers=passenger_headers, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["pnr"].startswith("PNR")
    assert len(data["pnr"]) == 10
    assert data["seat_number"] == 1
    assert data["fare"] == 650.0
    assert data["status"] == "CONFIRMED"
    assert data["payment_status"] == "PAID"


def test_booking_past_date_rejected(
    client: TestClient, passenger_headers: dict, sample_train: Train
):
    past_date = str(get_railway_operating_date() - timedelta(days=1))
    payload = {
        "train_id": sample_train.id,
        "journey_date": past_date,
        "source_station_code": "NDLS",
        "destination_station_code": "CNB",
    }
    response = client.post("/api/bookings", headers=passenger_headers, json=payload)
    assert response.status_code == 400
    assert "past dates" in response.json()["detail"].lower()


def test_booking_today_date_allowed(
    client: TestClient, passenger_headers: dict, sample_train: Train
):
    today_date = str(get_railway_operating_date())
    payload = {
        "train_id": sample_train.id,
        "journey_date": today_date,
        "source_station_code": "NDLS",
        "destination_station_code": "CNB",
    }
    response = client.post("/api/bookings", headers=passenger_headers, json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "CONFIRMED"
    assert response.json()["journey_date"] == today_date


def test_booking_future_date_allowed(
    client: TestClient, passenger_headers: dict, sample_train: Train
):
    future_date = str(get_railway_operating_date() + timedelta(days=1))
    payload = {
        "train_id": sample_train.id,
        "journey_date": future_date,
        "source_station_code": "NDLS",
        "destination_station_code": "CNB",
    }
    response = client.post("/api/bookings", headers=passenger_headers, json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "CONFIRMED"
    assert response.json()["journey_date"] == future_date



def test_booking_invalid_route_rejected(
    client: TestClient, passenger_headers: dict, sample_train: Train
):
    journey_date = str(get_railway_operating_date() + timedelta(days=10))
    # Reverse direction
    payload = {
        "train_id": sample_train.id,
        "journey_date": journey_date,
        "source_station_code": "LKO",
        "destination_station_code": "NDLS",
    }
    response = client.post("/api/bookings", headers=passenger_headers, json=payload)
    assert response.status_code == 400
    assert "does not operate" in response.json()["detail"].lower()


def test_cancellation_and_repeated_cancellation(
    client: TestClient,
    passenger_headers: dict,
    second_passenger_headers: dict,
    sample_train: Train,
):
    journey_date = str(get_railway_operating_date() + timedelta(days=12))
    # Book ticket
    book_res = client.post(
        "/api/bookings",
        headers=passenger_headers,
        json={
            "train_id": sample_train.id,
            "journey_date": journey_date,
            "source_station_code": "NDLS",
            "destination_station_code": "LKO",
        },
    )
    assert book_res.status_code == 201
    pnr = book_res.json()["pnr"]

    # Other passenger tries to cancel -> 403 Forbidden
    unauthorized_cancel = client.post(
        f"/api/bookings/{pnr}/cancel",
        headers=second_passenger_headers,
    )
    assert unauthorized_cancel.status_code == 403

    # Owner cancels -> Success
    cancel_res = client.post(
        f"/api/bookings/{pnr}/cancel",
        headers=passenger_headers,
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"
    assert cancel_res.json()["payment_status"] == "REFUNDED"

    # Repeated cancellation -> 400 Bad Request
    repeat_res = client.post(
        f"/api/bookings/{pnr}/cancel",
        headers=passenger_headers,
    )
    assert repeat_res.status_code == 400
    assert "already been cancelled" in repeat_res.json()["detail"].lower()


def test_availability_updates_on_booking_and_cancellation(
    client: TestClient,
    passenger_headers: dict,
    sample_train: Train,
):
    journey_date = str(get_railway_operating_date() + timedelta(days=14))

    # Initial availability: 5 seats
    avail1 = client.get(
        f"/api/trains/{sample_train.id}/availability",
        params={
            "source_station_code": "NDLS",
            "destination_station_code": "LKO",
            "journey_date": journey_date,
        },
    ).json()
    assert avail1["available_seats"] == 5

    # Book 1 ticket
    book_res = client.post(
        "/api/bookings",
        headers=passenger_headers,
        json={
            "train_id": sample_train.id,
            "journey_date": journey_date,
            "source_station_code": "NDLS",
            "destination_station_code": "LKO",
        },
    )
    assert book_res.status_code == 201
    pnr = book_res.json()["pnr"]

    # Availability drops to 4
    avail2 = client.get(
        f"/api/trains/{sample_train.id}/availability",
        params={
            "source_station_code": "NDLS",
            "destination_station_code": "LKO",
            "journey_date": journey_date,
        },
    ).json()
    assert avail2["available_seats"] == 4

    # Cancel ticket
    client.post(f"/api/bookings/{pnr}/cancel", headers=passenger_headers)

    # Availability restored to 5
    avail3 = client.get(
        f"/api/trains/{sample_train.id}/availability",
        params={
            "source_station_code": "NDLS",
            "destination_station_code": "LKO",
            "journey_date": journey_date,
        },
    ).json()
    assert avail3["available_seats"] == 5


def test_non_overlapping_intermediate_seat_reuse(
    client: TestClient,
    passenger_headers: dict,
    second_passenger_headers: dict,
    sample_train: Train,
):
    """
    CRITICAL DOMAIN TEST:
    Passenger 1: NDLS to ALIG (Stops 1 -> 3)
    Passenger 2: CNB to LKO (Stops 4 -> 5)
    Since segments do not overlap, Passenger 2 MUST be able to reuse the same physical seat!
    """
    journey_date = str(get_railway_operating_date() + timedelta(days=16))

    # Passenger 1 books NDLS to ALIG
    res1 = client.post(
        "/api/bookings",
        headers=passenger_headers,
        json={
            "train_id": sample_train.id,
            "journey_date": journey_date,
            "source_station_code": "NDLS",
            "destination_station_code": "ALIG",
        },
    )
    assert res1.status_code == 201
    seat1 = res1.json()["seat_number"]

    # Passenger 2 books CNB to LKO
    res2 = client.post(
        "/api/bookings",
        headers=second_passenger_headers,
        json={
            "train_id": sample_train.id,
            "journey_date": journey_date,
            "source_station_code": "CNB",
            "destination_station_code": "LKO",
        },
    )
    assert res2.status_code == 201
    seat2 = res2.json()["seat_number"]

    # Both should be assigned the exact same physical seat (seat 1) because their journeys do not overlap!
    assert seat1 == seat2 == 1


def test_overlapping_intermediate_seat_conflict(
    client: TestClient,
    passenger_headers: dict,
    second_passenger_headers: dict,
    sample_train: Train,
):
    """
    Passenger 1: NDLS to CNB (Stops 1 -> 4)
    Passenger 2: ALIG to LKO (Stops 3 -> 5)
    Overlaps on segment ALIG to CNB (Stops 3 -> 4).
    Must assign DIFFERENT seats!
    """
    journey_date = str(get_railway_operating_date() + timedelta(days=18))

    res1 = client.post(
        "/api/bookings",
        headers=passenger_headers,
        json={
            "train_id": sample_train.id,
            "journey_date": journey_date,
            "source_station_code": "NDLS",
            "destination_station_code": "CNB",
        },
    )
    assert res1.status_code == 201
    seat1 = res1.json()["seat_number"]

    res2 = client.post(
        "/api/bookings",
        headers=second_passenger_headers,
        json={
            "train_id": sample_train.id,
            "journey_date": journey_date,
            "source_station_code": "ALIG",
            "destination_station_code": "LKO",
        },
    )
    assert res2.status_code == 201
    seat2 = res2.json()["seat_number"]

    # Since they overlap, they CANNOT share the same physical seat
    assert seat1 != seat2


def test_midnight_boundary_immediately_before_and_after_ist(
    client: TestClient, passenger_headers: dict, sample_train: Train
):
    """
    Deterministic boundary test for midnight IST transition.
    Covers the date boundary immediately before and after midnight in Asia/Kolkata:
    1. At 23:59:59 IST on 2026-10-20 (18:29:59 UTC):
       - Today is 2026-10-20.
       - 2026-10-19 is rejected as past date (400).
       - 2026-10-20 is accepted as same-day journey (201).
       - 2026-10-21 is accepted as future journey (201).
    2. At 00:00:01 IST on 2026-10-21 (18:30:01 UTC on Oct 20):
       - Today is now 2026-10-21.
       - 2026-10-20 (accepted 2 seconds earlier) is now rejected as past date (400).
       - 2026-10-21 is accepted as same-day journey (201).
       - 2026-10-22 is accepted as future journey (201).
    """
    from unittest.mock import patch

    # --- Moment 1: 23:59:59 IST (Pre-midnight) ---
    with patch("app.services.booking_service.get_railway_operating_date", return_value=date(2026, 10, 20)):
        # Past date rejected
        res_past = client.post(
            "/api/bookings",
            headers=passenger_headers,
            json={
                "train_id": sample_train.id,
                "journey_date": "2026-10-19",
                "source_station_code": "NDLS",
                "destination_station_code": "CNB",
            },
        )
        assert res_past.status_code == 400
        assert "past dates" in res_past.json()["detail"].lower()

        # Same-day accepted
        res_today = client.post(
            "/api/bookings",
            headers=passenger_headers,
            json={
                "train_id": sample_train.id,
                "journey_date": "2026-10-20",
                "source_station_code": "NDLS",
                "destination_station_code": "CNB",
            },
        )
        assert res_today.status_code == 201
        assert res_today.json()["status"] == "CONFIRMED"

        # Future date accepted
        res_future = client.post(
            "/api/bookings",
            headers=passenger_headers,
            json={
                "train_id": sample_train.id,
                "journey_date": "2026-10-21",
                "source_station_code": "NDLS",
                "destination_station_code": "CNB",
            },
        )
        assert res_future.status_code == 201
        assert res_future.json()["status"] == "CONFIRMED"

    # --- Moment 2: 00:00:01 IST (Post-midnight) ---
    with patch("app.services.booking_service.get_railway_operating_date", return_value=date(2026, 10, 21)):
        # 2026-10-20 is now in the past and MUST be rejected
        res_past_now = client.post(
            "/api/bookings",
            headers=passenger_headers,
            json={
                "train_id": sample_train.id,
                "journey_date": "2026-10-20",
                "source_station_code": "NDLS",
                "destination_station_code": "CNB",
            },
        )
        assert res_past_now.status_code == 400
        assert "past dates" in res_past_now.json()["detail"].lower()

        # 2026-10-21 is now same-day and accepted
        res_today_now = client.post(
            "/api/bookings",
            headers=passenger_headers,
            json={
                "train_id": sample_train.id,
                "journey_date": "2026-10-21",
                "source_station_code": "NDLS",
                "destination_station_code": "CNB",
            },
        )
        assert res_today_now.status_code == 201
        assert res_today_now.json()["status"] == "CONFIRMED"


def test_railway_operating_date_kolkata_timezone_behavior():
    """
    Test that get_railway_operating_date explicitly follows Asia/Kolkata regardless
    of UTC or foreign host timezone clock values.
    """
    from datetime import datetime, timezone
    from unittest.mock import patch
    from app.services.booking_service import get_railway_operating_date, RAILWAY_TIMEZONE

    assert str(RAILWAY_TIMEZONE) == "Asia/Kolkata"

    # Mock datetime.now inside booking_service to simulate host running at 19:00 UTC (Oct 20)
    # which is 00:30 IST on Oct 21.
    with patch("app.services.booking_service.datetime") as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: (
            datetime(2026, 10, 20, 19, 0, 0, tzinfo=timezone.utc).astimezone(tz)
            if tz else datetime(2026, 10, 20, 19, 0, 0)
        )
        operating_date = get_railway_operating_date()
        # Even though UTC date is 2026-10-20, IST operating date MUST be 2026-10-21
        assert operating_date == date(2026, 10, 21)

