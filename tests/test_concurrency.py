import concurrent.futures
import threading
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.train import Train
from app.models.booking import Booking, BookingStatus
from app.models.user import User, UserRole
from app.security.password import hash_password
from app.security.jwt import create_access_token


def _create_test_passenger(session: Session, email: str, name: str) -> dict:
    user = session.exec(select(User).where(User.email == email)).first()
    if not user:
        user = User(
            name=name,
            email=email,
            hashed_password=hash_password("Pass123!"),
            role=UserRole.PASSENGER,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    token_dict = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    return {"Authorization": f"Bearer {token_dict['token']}"}


def test_concurrent_booking_last_seat(
    client: TestClient, session: Session, sample_train: Train
):
    """
    Test 2 concurrent passenger requests competing for the 1 final seat.
    Expected outcome: Exactly 1 succeeds (201 Created), exactly 1 gets 409 Conflict.
    No double booking in database.
    """
    # Ensure test passengers exist before creating bookings
    headers_p1 = _create_test_passenger(session, "comp1@test.com", "Competitor 1")
    headers_p2 = _create_test_passenger(session, "comp2@test.com", "Competitor 2")
    user_p1 = session.exec(select(User).where(User.email == "comp1@test.com")).first()

    journey_date = str(date.today() + timedelta(days=25))
    src_stop = sorted(sample_train.stops, key=lambda s: s.stop_order)[0]
    dst_stop = sorted(sample_train.stops, key=lambda s: s.stop_order)[-1]

    # Pre-book 4 seats on sample_train (total_seats = 5)
    for seat_num in range(1, 5):
        b = Booking(
            pnr=f"PNRPRE00{seat_num}",
            user_id=user_p1.id,
            train_id=sample_train.id,
            journey_date=date.fromisoformat(journey_date),
            seat_number=seat_num,
            source_station_id=src_stop.station_id,
            destination_station_id=dst_stop.station_id,
            source_stop_order=src_stop.stop_order,
            destination_stop_order=dst_stop.stop_order,
            fare=820.0,
            status=BookingStatus.CONFIRMED,
        )
        session.add(b)
    session.commit()

    payload = {
        "train_id": sample_train.id,
        "journey_date": journey_date,
        "source_station_code": "NDLS",
        "destination_station_code": "LKO",
    }

    results = []

    def make_booking(headers):
        res = client.post("/api/bookings", headers=headers, json=payload)
        return res.status_code, res.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(make_booking, headers_p1)
        f2 = executor.submit(make_booking, headers_p2)
        results = [f1.result(), f2.result()]

    status_codes = [r[0] for r in results]
    assert 201 in status_codes
    assert 409 in status_codes

    # Verify database state
    active_bookings = session.exec(
        select(Booking).where(
            Booking.train_id == sample_train.id,
            Booking.journey_date == date.fromisoformat(journey_date),
            Booking.status == BookingStatus.CONFIRMED,
        )
    ).all()

    # Total confirmed bookings must be exactly 5 (4 pre-booked + 1 successful)
    assert len(active_bookings) == 5
    assigned_seats = [b.seat_number for b in active_bookings]
    assert sorted(assigned_seats) == [1, 2, 3, 4, 5]


def test_concurrent_multiple_passengers_exceeding_capacity(
    client: TestClient, session: Session, sample_train: Train
):
    """
    Test 10 concurrent requests for a fresh train with 5 total seats.
    Expected outcome: Exactly 5 succeed (201 Created), exactly 5 fail (409 Conflict).
    All 5 successful bookings receive distinct seat numbers (1 to 5).
    """
    journey_date = str(date.today() + timedelta(days=28))

    passengers_headers = [
        _create_test_passenger(session, f"batch_{i}@test.com", f"Batch Passenger {i}")
        for i in range(10)
    ]

    payload = {
        "train_id": sample_train.id,
        "journey_date": journey_date,
        "source_station_code": "NDLS",
        "destination_station_code": "LKO",
    }

    def book_request(headers):
        res = client.post("/api/bookings", headers=headers, json=payload)
        return res.status_code, res.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(book_request, h) for h in passengers_headers]
        results = [f.result() for f in futures]

    successes = [r for r in results if r[0] == 201]
    conflicts = [r for r in results if r[0] == 409]

    assert len(successes) == 5
    assert len(conflicts) == 5

    # Check distinct seat numbers
    allocated_seats = [r[1]["seat_number"] for r in successes]
    assert len(set(allocated_seats)) == 5
    assert sorted(allocated_seats) == [1, 2, 3, 4, 5]

    # Verify database
    db_bookings = session.exec(
        select(Booking).where(
            Booking.train_id == sample_train.id,
            Booking.journey_date == date.fromisoformat(journey_date),
            Booking.status == BookingStatus.CONFIRMED,
        )
    ).all()
    assert len(db_bookings) == 5


def test_concurrent_cancellation_and_booking_race(
    client: TestClient, session: Session, sample_train: Train
):
    """
    Test a cancellation occurring concurrently with a new booking attempt.
    """
    journey_date = str(date.today() + timedelta(days=32))
    p1_headers = _create_test_passenger(session, "race_p1@test.com", "Race P1")
    p2_headers = _create_test_passenger(session, "race_p2@test.com", "Race P2")

    # Fill all 5 seats
    pnrs = []
    for _ in range(5):
        res = client.post(
            "/api/bookings",
            headers=p1_headers,
            json={
                "train_id": sample_train.id,
                "journey_date": journey_date,
                "source_station_code": "NDLS",
                "destination_station_code": "LKO",
            },
        )
        assert res.status_code == 201
        pnrs.append(res.json()["pnr"])

    # Now train is full.
    # Concurrently cancel one booking and have p2 attempt to book.
    pnr_to_cancel = pnrs[0]

    def cancel_task():
        return client.post(f"/api/bookings/{pnr_to_cancel}/cancel", headers=p1_headers)

    def book_task():
        return client.post(
            "/api/bookings",
            headers=p2_headers,
            json={
                "train_id": sample_train.id,
                "journey_date": journey_date,
                "source_station_code": "NDLS",
                "destination_station_code": "LKO",
            },
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_cancel = executor.submit(cancel_task)
        f_book = executor.submit(book_task)
        res_cancel = f_cancel.result()
        res_book = f_book.result()

    assert res_cancel.status_code == 200
    # The booking either successfully grabbed the freed seat or arrived before cancellation
    assert res_book.status_code in [201, 409]

    # Database invariant check: active bookings count must never exceed 5
    active_count = len(
        session.exec(
            select(Booking).where(
                Booking.train_id == sample_train.id,
                Booking.journey_date == date.fromisoformat(journey_date),
                Booking.status == BookingStatus.CONFIRMED,
            )
        ).all()
    )
    assert active_count <= 5


def test_concurrent_duplicate_cancellation_race(
    client: TestClient, session: Session, sample_train: Train
):
    """
    Test two concurrent requests attempting to cancel the same confirmed booking.
    Uses threading.Barrier to deterministically synchronize and fire both requests simultaneously.
    Expected outcome:
    - Exactly 1 request succeeds with 200 OK and status CANCELLED.
    - Exactly 1 request fails with 400 Bad Request indicating already cancelled.
    - Subsequent repeated cancellation returns 400 Bad Request.
    - Database booking state is CANCELLED with REFUNDED payment status.
    - Seat availability is preserved and no data corruption occurs.
    """
    journey_date = str(date.today() + timedelta(days=35))
    headers = _create_test_passenger(session, "cancel_race@test.com", "Cancel Racer")

    # Book a ticket
    book_res = client.post(
        "/api/bookings",
        headers=headers,
        json={
            "train_id": sample_train.id,
            "journey_date": journey_date,
            "source_station_code": "NDLS",
            "destination_station_code": "LKO",
        },
    )
    assert book_res.status_code == 201
    pnr = book_res.json()["pnr"]

    barrier = threading.Barrier(2)

    def cancel_attempt():
        # Deterministically wait for both threads to reach this point before requesting
        barrier.wait()
        res = client.post(f"/api/bookings/{pnr}/cancel", headers=headers)
        return res.status_code, res.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(cancel_attempt)
        f2 = executor.submit(cancel_attempt)
        res1 = f1.result()
        res2 = f2.result()

    status_codes = [res1[0], res2[0]]
    assert 200 in status_codes, f"Expected one 200 OK, got: {status_codes}"
    assert 400 in status_codes, f"Expected one 400 Bad Request, got: {status_codes}"

    bad_res = res1 if res1[0] == 400 else res2
    assert "already been cancelled" in bad_res[1]["detail"].lower()

    # Repeated cancellation attempt after the race should also be rejected with 400
    subsequent_res = client.post(f"/api/bookings/{pnr}/cancel", headers=headers)
    assert subsequent_res.status_code == 400
    assert "already been cancelled" in subsequent_res.json()["detail"].lower()

    # Verify database state
    db_booking = session.exec(select(Booking).where(Booking.pnr == pnr)).first()
    assert db_booking.status == BookingStatus.CANCELLED
    assert db_booking.payment_status.value == "REFUNDED"
    assert db_booking.cancelled_at is not None


def test_cancellation_transient_sqlite_lock_retry(session: Session, sample_train: Train):
    """
    Test that BookingService.cancel_booking catches transient SQLite lock contention
    ('database is locked'), cleanly rolls back the failed transaction state,
    retries, and successfully cancels the booking on the subsequent attempt.
    """
    from unittest.mock import patch
    from sqlalchemy.exc import OperationalError
    from app.services.booking_service import BookingService

    journey_date = date.today() + timedelta(days=36)
    user = session.exec(select(User).where(User.email == "cancel_retry@test.com")).first()
    if not user:
        user = User(
            name="Retry Passenger",
            email="cancel_retry@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.PASSENGER,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    booking = Booking(
        pnr="PNRRETRY01",
        user_id=user.id,
        train_id=sample_train.id,
        journey_date=journey_date,
        seat_number=1,
        source_station_id=sample_train.stops[0].station_id,
        destination_station_id=sample_train.stops[-1].station_id,
        source_stop_order=1,
        destination_stop_order=5,
        fare=820.0,
        status=BookingStatus.CONFIRMED,
    )
    session.add(booking)
    session.commit()
    session.refresh(booking)

    original_commit = session.commit
    call_count = 0

    def mock_commit():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OperationalError("database is locked", None, None)
        return original_commit()

    with patch.object(session, "commit", side_effect=mock_commit):
        cancelled = BookingService.cancel_booking(session, user, "PNRRETRY01")

    assert cancelled.status == BookingStatus.CANCELLED
    assert cancelled.payment_status.value == "REFUNDED"
    assert call_count == 2


def test_cancellation_non_transient_error_not_retried(session: Session, sample_train: Train):
    """
    Test that BookingService.cancel_booking does NOT retry non-transient OperationalErrors
    (such as schema, disk corruption, or syntax errors), re-raising them immediately.
    """
    from unittest.mock import patch
    import pytest
    from sqlalchemy.exc import OperationalError
    from app.services.booking_service import BookingService

    journey_date = date.today() + timedelta(days=37)
    user = session.exec(select(User).where(User.email == "cancel_nontrans@test.com")).first()
    if not user:
        user = User(
            name="NonTransient Passenger",
            email="cancel_nontrans@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.PASSENGER,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    booking = Booking(
        pnr="PNRNONTRANS",
        user_id=user.id,
        train_id=sample_train.id,
        journey_date=journey_date,
        seat_number=2,
        source_station_id=sample_train.stops[0].station_id,
        destination_station_id=sample_train.stops[-1].station_id,
        source_stop_order=1,
        destination_stop_order=5,
        fare=820.0,
        status=BookingStatus.CONFIRMED,
    )
    session.add(booking)
    session.commit()
    session.refresh(booking)

    call_count = 0

    def mock_commit():
        nonlocal call_count
        call_count += 1
        raise OperationalError("disk I/O error: corrupted block", None, None)

    with patch.object(session, "commit", side_effect=mock_commit):
        with pytest.raises(OperationalError) as exc_info:
            BookingService.cancel_booking(session, user, "PNRNONTRANS")

    assert "disk i/o error" in str(exc_info.value).lower()
    assert call_count == 1


def test_cancellation_exhausted_retries_raises_503(session: Session, sample_train: Train):
    """
    Test that BookingService.cancel_booking raises 503 Service Unavailable when
    transient SQLite lock contention persists across all bounded retry attempts.
    """
    from unittest.mock import patch
    import pytest
    from fastapi import HTTPException
    from sqlalchemy.exc import OperationalError
    from app.services.booking_service import BookingService

    journey_date = date.today() + timedelta(days=38)
    user = session.exec(select(User).where(User.email == "cancel_503@test.com")).first()
    if not user:
        user = User(
            name="503 Passenger",
            email="cancel_503@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.PASSENGER,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    booking = Booking(
        pnr="PNR503FAIL",
        user_id=user.id,
        train_id=sample_train.id,
        journey_date=journey_date,
        seat_number=3,
        source_station_id=sample_train.stops[0].station_id,
        destination_station_id=sample_train.stops[-1].station_id,
        source_stop_order=1,
        destination_stop_order=5,
        fare=820.0,
        status=BookingStatus.CONFIRMED,
    )
    session.add(booking)
    session.commit()
    session.refresh(booking)

    call_count = 0

    def mock_commit():
        nonlocal call_count
        call_count += 1
        raise OperationalError("database is locked", None, None)

    with patch.object(session, "commit", side_effect=mock_commit):
        with pytest.raises(HTTPException) as exc_info:
            BookingService.cancel_booking(session, user, "PNR503FAIL")

    assert exc_info.value.status_code == 503
    assert "high cancellation concurrency" in exc_info.value.detail.lower()
    assert call_count == 5


def test_cancellation_begin_immediate_transient_lock_retry(session: Session, sample_train: Train):
    """
    Test that BookingService.cancel_booking catches transient lock contention on
    BEGIN IMMEDIATE, cleanly rolls back, retries, and succeeds.
    """
    from unittest.mock import patch
    from sqlalchemy.exc import OperationalError
    from app.services.booking_service import BookingService

    journey_date = date.today() + timedelta(days=39)
    user = session.exec(select(User).where(User.email == "cancel_bi@test.com")).first()
    if not user:
        user = User(
            name="BI Passenger",
            email="cancel_bi@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.PASSENGER,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    booking = Booking(
        pnr="PNRBITEST01",
        user_id=user.id,
        train_id=sample_train.id,
        journey_date=journey_date,
        seat_number=4,
        source_station_id=sample_train.stops[0].station_id,
        destination_station_id=sample_train.stops[-1].station_id,
        source_stop_order=1,
        destination_stop_order=5,
        fare=820.0,
        status=BookingStatus.CONFIRMED,
    )
    session.add(booking)
    session.commit()
    session.refresh(booking)

    original_exec = session.exec
    bi_call_count = 0

    def mock_exec(statement, *args, **kwargs):
        nonlocal bi_call_count
        stmt_str = str(statement)
        if "BEGIN IMMEDIATE" in stmt_str:
            bi_call_count += 1
            if bi_call_count == 1:
                raise OperationalError("database is locked", None, None)
        return original_exec(statement, *args, **kwargs)

    with patch.object(session, "exec", side_effect=mock_exec):
        cancelled = BookingService.cancel_booking(session, user, "PNRBITEST01")

    assert cancelled.status == BookingStatus.CANCELLED
    assert cancelled.payment_status.value == "REFUNDED"
    assert bi_call_count == 2


def test_book_ticket_transient_sqlite_lock_retry(session: Session, sample_train: Train):
    """
    Test that BookingService.book_ticket retries on transient SQLite lock error and succeeds.
    """
    from unittest.mock import patch
    from sqlalchemy.exc import OperationalError
    from app.services.booking_service import BookingService
    from app.schemas.booking import BookingCreateRequest

    journey_date = date.today() + timedelta(days=40)
    user = session.exec(select(User).where(User.email == "book_retry@test.com")).first()
    if not user:
        user = User(
            name="Book Retry Passenger",
            email="book_retry@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.PASSENGER,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    req = BookingCreateRequest(
        train_id=sample_train.id,
        journey_date=journey_date,
        source_station_code="NDLS",
        destination_station_code="LKO",
    )

    original_commit = session.commit
    call_count = 0

    def mock_commit():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OperationalError("database is locked", None, None)
        return original_commit()

    with patch.object(session, "commit", side_effect=mock_commit):
        booked = BookingService.book_ticket(session, user, req)

    assert booked.status == BookingStatus.CONFIRMED
    assert call_count == 2


def test_book_ticket_exhausted_retries_raises_503(session: Session, sample_train: Train):
    """
    Test that BookingService.book_ticket raises 503 when lock errors persist.
    """
    from unittest.mock import patch
    import pytest
    from fastapi import HTTPException
    from sqlalchemy.exc import OperationalError
    from app.services.booking_service import BookingService
    from app.schemas.booking import BookingCreateRequest

    journey_date = date.today() + timedelta(days=41)
    user = session.exec(select(User).where(User.email == "book_503@test.com")).first()
    if not user:
        user = User(
            name="Book 503 Passenger",
            email="book_503@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.PASSENGER,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    req = BookingCreateRequest(
        train_id=sample_train.id,
        journey_date=journey_date,
        source_station_code="NDLS",
        destination_station_code="LKO",
    )

    call_count = 0

    def mock_commit():
        nonlocal call_count
        call_count += 1
        raise OperationalError("database is locked", None, None)

    with patch.object(session, "commit", side_effect=mock_commit):
        with pytest.raises(HTTPException) as exc_info:
            BookingService.book_ticket(session, user, req)

    assert exc_info.value.status_code == 503
    assert call_count == 5


def test_book_ticket_non_transient_error_not_retried(session: Session, sample_train: Train):
    """
    Test that BookingService.book_ticket re-raises non-transient OperationalError immediately.
    """
    from unittest.mock import patch
    import pytest
    from sqlalchemy.exc import OperationalError
    from app.services.booking_service import BookingService
    from app.schemas.booking import BookingCreateRequest

    journey_date = date.today() + timedelta(days=42)
    user = session.exec(select(User).where(User.email == "book_nontrans@test.com")).first()
    if not user:
        user = User(
            name="Book NonTrans Passenger",
            email="book_nontrans@test.com",
            hashed_password=hash_password("Pass123!"),
            role=UserRole.PASSENGER,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    req = BookingCreateRequest(
        train_id=sample_train.id,
        journey_date=journey_date,
        source_station_code="NDLS",
        destination_station_code="LKO",
    )

    call_count = 0

    def mock_commit():
        nonlocal call_count
        call_count += 1
        raise OperationalError("disk I/O error", None, None)

    with patch.object(session, "commit", side_effect=mock_commit):
        with pytest.raises(OperationalError) as exc_info:
            BookingService.book_ticket(session, user, req)

    assert "disk i/o error" in str(exc_info.value).lower()
    assert call_count == 1


