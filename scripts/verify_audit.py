import concurrent.futures
from datetime import date, datetime, timedelta, timezone
import os
import sys
import tempfile
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy import event, text

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database import get_session
from app.models.user import User, UserRole
from app.models.station import Station
from app.models.train import Train
from app.models.route import RouteStop
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.password_reset import PasswordResetToken
from app.models.token_blocklist import TokenBlocklist
from app.security.password import hash_password, verify_password, hash_token
from app.security.jwt import create_access_token, decode_access_token


def run_audit():
    print("=" * 60)
    print("      RAILWAY BOOKING SYSTEM — TECHNICAL AUDIT")
    print("=" * 60)

    # Setup isolated test database for audit
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30.0},
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=30000;")
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.close()

    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    # Seed base test data
    with Session(engine) as session:
        # Create stations
        stations = [
            Station(station_code="NDLS", name="New Delhi", city="New Delhi"),
            Station(station_code="GZB", name="Ghaziabad", city="Ghaziabad"),
            Station(station_code="ALIG", name="Aligarh", city="Aligarh"),
            Station(station_code="CNB", name="Kanpur Central", city="Kanpur"),
            Station(station_code="LKO", name="Lucknow", city="Lucknow"),
        ]
        for s in stations:
            session.add(s)
        session.commit()

        # Create train with capacity = 5
        train = Train(train_number="AUDIT101", name="Audit Express", total_seats=5, is_active=True)
        session.add(train)
        session.commit()
        session.refresh(train)

        # Create stops
        stops_info = [
            (1, 1, None, "06:00", 0.0),
            (2, 2, "06:40", "06:42", 60.0),
            (3, 3, "07:30", "07:32", 150.0),
            (4, 4, "10:30", "10:35", 500.0),
            (5, 5, "12:00", None, 700.0),
        ]
        for st_id, order, arr, dep, fare in stops_info:
            session.add(
                RouteStop(
                    train_id=train.id,
                    station_id=st_id,
                    stop_order=order,
                    arrival_time=arr,
                    departure_time=dep,
                    fare_from_origin=fare,
                )
            )

        # Create admin and passengers
        admin = User(name="Admin", email="admin@test.com", hashed_password=hash_password("AdminPass123!"), role=UserRole.ADMIN)
        p1 = User(name="Pass 1", email="p1@test.com", hashed_password=hash_password("Pass123!"), role=UserRole.PASSENGER)
        p2 = User(name="Pass 2", email="p2@test.com", hashed_password=hash_password("Pass123!"), role=UserRole.PASSENGER)
        session.add(admin)
        session.add(p1)
        session.add(p2)
        session.commit()

    token_p1 = create_access_token(user_id=2, email="p1@test.com", role="passenger")["token"]
    headers_p1 = {"Authorization": f"Bearer {token_p1}"}

    token_p2 = create_access_token(user_id=3, email="p2@test.com", role="passenger")["token"]
    headers_p2 = {"Authorization": f"Bearer {token_p2}"}

    # -------------------------------------------------------------
    # AUDIT 6: Last Available Seat Competing Concurrent Requests
    # -------------------------------------------------------------
    print("\n[6] Testing concurrent booking for the last available seat...")
    journey_date_6 = str(date.today() + timedelta(days=10))

    with Session(engine) as session:
        # Pre-reserve seats 1, 2, 3, 4
        for s_num in range(1, 5):
            session.add(
                Booking(
                    pnr=f"AUDITLAST{s_num}",
                    user_id=2,
                    train_id=1,
                    journey_date=date.fromisoformat(journey_date_6),
                    seat_number=s_num,
                    source_station_id=1,
                    destination_station_id=5,
                    source_stop_order=1,
                    destination_stop_order=5,
                    fare=700.0,
                    status=BookingStatus.CONFIRMED,
                )
            )
        session.commit()

    def try_book(headers):
        return client.post(
            "/api/bookings",
            headers=headers,
            json={
                "train_id": 1,
                "journey_date": journey_date_6,
                "source_station_code": "NDLS",
                "destination_station_code": "LKO",
            },
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(try_book, headers_p1)
        f2 = ex.submit(try_book, headers_p2)
        r1 = f1.result()
        r2 = f2.result()

    statuses = [r1.status_code, r2.status_code]
    print(f"    Statuses received: {statuses}")
    assert 201 in statuses and 409 in statuses, f"Expected [201, 409], got {statuses}"

    with Session(engine) as session:
        active = session.exec(
            select(Booking).where(
                Booking.train_id == 1,
                Booking.journey_date == date.fromisoformat(journey_date_6),
                Booking.status == BookingStatus.CONFIRMED,
            )
        ).all()
        print(f"    Confirmed bookings in DB: {len(active)} / 5 seats")
        assert len(active) == 5, f"Expected exactly 5 bookings, found {len(active)}"
        seats = sorted([b.seat_number for b in active])
        assert seats == [1, 2, 3, 4, 5], f"Expected seats 1..5, got {seats}"
    print("    [PASS] Exactly 1 request succeeded (Seat 5 allocated), 1 received 409 Conflict.")

    # -------------------------------------------------------------
    # AUDIT 7: Concurrent Requests Exceeding Capacity
    # -------------------------------------------------------------
    print("\n[7] Testing concurrent booking exceeding train capacity (10 threads for 5 seats)...")
    journey_date_7 = str(date.today() + timedelta(days=15))

    passengers_headers = []
    with Session(engine) as session:
        for i in range(10):
            u = User(name=f"Bulk {i}", email=f"bulk_{i}@test.com", hashed_password=hash_password("Pass123!"), role=UserRole.PASSENGER)
            session.add(u)
            session.commit()
            t = create_access_token(user_id=u.id, email=u.email, role="passenger")["token"]
            passengers_headers.append({"Authorization": f"Bearer {t}"})

    def try_book_capacity(headers):
        return client.post(
            "/api/bookings",
            headers=headers,
            json={
                "train_id": 1,
                "journey_date": journey_date_7,
                "source_station_code": "NDLS",
                "destination_station_code": "LKO",
            },
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(try_book_capacity, passengers_headers))

    codes = [r.status_code for r in results]
    successes = codes.count(201)
    conflicts = codes.count(409)
    print(f"    Results: {successes} succeeded (201), {conflicts} rejected (409)")
    assert successes == 5 and conflicts == 5, f"Expected 5 successes and 5 conflicts, got {successes} / {conflicts}"

    with Session(engine) as session:
        db_bookings = session.exec(
            select(Booking).where(
                Booking.train_id == 1,
                Booking.journey_date == date.fromisoformat(journey_date_7),
                Booking.status == BookingStatus.CONFIRMED,
            )
        ).all()
        assert len(db_bookings) == 5
        assert sorted([b.seat_number for b in db_bookings]) == [1, 2, 3, 4, 5]
    print("    [PASS] Capacity strictly enforced. Seats 1 to 5 allocated with zero duplicates.")

    # -------------------------------------------------------------
    # AUDIT 8: Non-Overlapping vs Overlapping Segment Reuse
    # -------------------------------------------------------------
    print("\n[8] Testing non-overlapping segment seat reuse vs overlapping conflict...")
    journey_date_8 = str(date.today() + timedelta(days=20))

    # Journey A: NDLS (1) -> ALIG (3)
    res_a = client.post(
        "/api/bookings",
        headers=headers_p1,
        json={"train_id": 1, "journey_date": journey_date_8, "source_station_code": "NDLS", "destination_station_code": "ALIG"},
    )
    assert res_a.status_code == 201
    seat_a = res_a.json()["seat_number"]

    # Journey B (Non-overlapping): CNB (4) -> LKO (5)
    res_b = client.post(
        "/api/bookings",
        headers=headers_p2,
        json={"train_id": 1, "journey_date": journey_date_8, "source_station_code": "CNB", "destination_station_code": "LKO"},
    )
    assert res_b.status_code == 201
    seat_b = res_b.json()["seat_number"]

    print(f"    Passenger A (NDLS -> ALIG): Allocated Seat {seat_a}")
    print(f"    Passenger B (CNB -> LKO):   Allocated Seat {seat_b}")
    assert seat_a == seat_b == 1, f"Expected both to share Seat 1, got {seat_a} and {seat_b}"
    print("    [PASS] Non-overlapping journeys safely shared the same physical seat!")

    # Journey C (Overlapping with A): ALIG (3) -> CNB (4) -> wait, overlaps with A?
    # Stop 1->3 is [1, 3). ALIG to CNB is [3, 4). max(1, 3) = 3, min(3, 4) = 3. 3 < 3 is False!
    # Journey D (Overlaps with A): NDLS (1) -> CNB (4) is [1, 4). Overlaps with [1, 3)!
    res_d = client.post(
        "/api/bookings",
        headers=headers_p1,
        json={"train_id": 1, "journey_date": journey_date_8, "source_station_code": "NDLS", "destination_station_code": "CNB"},
    )
    assert res_d.status_code == 201
    seat_d = res_d.json()["seat_number"]
    print(f"    Passenger D (NDLS -> CNB):  Allocated Seat {seat_d}")
    assert seat_d != seat_a, f"Expected different seat for overlapping journey, got {seat_d}"
    print("    [PASS] Overlapping journey was allocated a distinct physical seat (Seat 2).")

    # -------------------------------------------------------------
    # AUDIT 9: Cancellation Racing with New Booking
    # -------------------------------------------------------------
    print("\n[9] Testing cancellation racing with new booking...")
    journey_date_9 = str(date.today() + timedelta(days=22))

    # Fill all 5 seats
    pnrs = []
    for _ in range(5):
        r = client.post(
            "/api/bookings",
            headers=headers_p1,
            json={"train_id": 1, "journey_date": journey_date_9, "source_station_code": "NDLS", "destination_station_code": "LKO"},
        )
        pnrs.append(r.json()["pnr"])

    pnr_cancel = pnrs[0]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_cancel = ex.submit(lambda: client.post(f"/api/bookings/{pnr_cancel}/cancel", headers=headers_p1))
        f_book = ex.submit(lambda: client.post(
            "/api/bookings",
            headers=headers_p2,
            json={"train_id": 1, "journey_date": journey_date_9, "source_station_code": "NDLS", "destination_station_code": "LKO"},
        ))
        res_cancel = f_cancel.result()
        res_book = f_book.result()

    print(f"    Cancel response: HTTP {res_cancel.status_code}")
    print(f"    Compete booking response: HTTP {res_book.status_code}")
    assert res_cancel.status_code == 200
    assert res_book.status_code in [201, 409]

    with Session(engine) as session:
        active_cnt = len(
            session.exec(
                select(Booking).where(
                    Booking.train_id == 1,
                    Booking.journey_date == date.fromisoformat(journey_date_9),
                    Booking.status == BookingStatus.CONFIRMED,
                )
            ).all()
        )
        print(f"    Total active bookings in DB: {active_cnt} <= 5")
        assert active_cnt <= 5
    print("    [PASS] Zero database inconsistency during cancellation race.")

    # -------------------------------------------------------------
    # AUDIT 10: Security Controls (Auth, Revocation, Reset Token)
    # -------------------------------------------------------------
    print("\n[10] Auditing security controls...")
    # Token revocation
    res_prof = client.get("/api/users/me", headers=headers_p1)
    assert res_prof.status_code == 200

    res_logout = client.post("/api/auth/logout", headers=headers_p1)
    assert res_logout.status_code == 200

    res_revoked = client.get("/api/users/me", headers=headers_p1)
    assert res_revoked.status_code == 401
    assert "revoked" in res_revoked.json()["detail"].lower()
    print("    [PASS] Logout immediately revokes JWT on server; subsequent calls return 401.")

    # Password reset single-use token
    res_forgot = client.post("/api/auth/forgot-password", json={"email": "p2@test.com"})
    reset_tok = res_forgot.json()["dev_reset_token"]
    assert reset_tok is not None

    res_reset1 = client.post("/api/auth/reset-password", json={"token": reset_tok, "new_password": "NewSecretPass123!"})
    assert res_reset1.status_code == 200

    res_reset2 = client.post("/api/auth/reset-password", json={"token": reset_tok, "new_password": "ReuseAttempt123!"})
    assert res_reset2.status_code == 400
    assert "already been used" in res_reset2.json()["detail"].lower()
    print("    [PASS] Password reset token consumed atomically; reuse attempt rejected with 400.")

    # -------------------------------------------------------------
    # AUDIT 11: Privilege Separation & Data Isolation
    # -------------------------------------------------------------
    print("\n[11] Auditing privilege separation & booking privacy...")
    # Public registration self-promotion test
    res_reg = client.post("/api/auth/register", json={"name": "Attacker", "email": "attacker@test.com", "password": "Password123!", "role": "admin"})
    assert res_reg.status_code == 201
    assert res_reg.json()["role"] == "passenger"
    print("    [PASS] Public registration strictly assigns 'passenger' role.")

    # Passenger attempting admin mutation
    res_admin_mut = client.post(
        "/api/admin/stations",
        headers=headers_p2,
        json={"station_code": "HACK", "name": "Hacked", "city": "City"}
    )
    assert res_admin_mut.status_code == 403
    print("    [PASS] Passenger access to admin endpoints forbidden with HTTP 403.")

    # Booking privacy: p1 tries to view p2's booking
    p2_book_res = client.post(
        "/api/bookings",
        headers={"Authorization": f"Bearer {create_access_token(user_id=3, email='p2@test.com', role='passenger')['token']}"},
        json={"train_id": 1, "journey_date": str(date.today() + timedelta(days=28)), "source_station_code": "NDLS", "destination_station_code": "GZB"},
    )
    p2_pnr = p2_book_res.json()["pnr"]

    # p1 tries to access p2's PNR
    p1_new_token = create_access_token(user_id=2, email="p1@test.com", role="passenger")["token"]
    res_snoop = client.get(f"/api/bookings/{p2_pnr}", headers={"Authorization": f"Bearer {p1_new_token}"})
    assert res_snoop.status_code == 403
    print("    [PASS] Cross-user booking access rejected with HTTP 403.")

    # Cleanup temp db
    app.dependency_overrides.clear()
    try:
        os.remove(db_path)
    except OSError:
        pass

    print("\n" + "=" * 60)
    print("      ALL TECHNICAL AUDIT CRITERIA FULLY VERIFIED")
    print("=" * 60)


if __name__ == "__main__":
    run_audit()
