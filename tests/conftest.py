import os
import sys
import tempfile
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy import event

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database import get_session
from app.models.user import User, UserRole
from app.models.station import Station
from app.models.train import Train
from app.models.route import RouteStop
from app.security.password import hash_password
from app.security.jwt import create_access_token


@pytest.fixture(scope="session")
def test_db_path() -> Generator[str, None, None]:
    """Create a temporary SQLite database file for testing concurrency and isolation."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture(scope="session")
def test_engine(test_db_path: str):
    engine = create_engine(
        f"sqlite:///{test_db_path}",
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
    return engine


@pytest.fixture
def session(test_engine) -> Generator[Session, None, None]:
    """Yield a database session and clean tables after test execution."""
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def client(test_engine) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with overridden database session."""
    def override_get_session():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(session: Session) -> User:
    user = session.exec(select(User).where(User.email == "test_admin@railway.local")).first()
    if not user:
        user = User(
            name="Admin User",
            email="test_admin@railway.local",
            hashed_password=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user: User) -> dict:
    token_dict = create_access_token(
        user_id=admin_user.id,
        email=admin_user.email,
        role=admin_user.role.value,
    )
    return {"Authorization": f"Bearer {token_dict['token']}"}


@pytest.fixture
def passenger_user(session: Session) -> User:
    user = session.exec(select(User).where(User.email == "passenger1@example.com")).first()
    if not user:
        user = User(
            name="Rahul Sharma",
            email="passenger1@example.com",
            hashed_password=hash_password("PassengerPass123!"),
            role=UserRole.PASSENGER,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


@pytest.fixture
def passenger_headers(passenger_user: User) -> dict:
    token_dict = create_access_token(
        user_id=passenger_user.id,
        email=passenger_user.email,
        role=passenger_user.role.value,
    )
    return {"Authorization": f"Bearer {token_dict['token']}"}


@pytest.fixture
def second_passenger_user(session: Session) -> User:
    user = session.exec(select(User).where(User.email == "passenger2@example.com")).first()
    if not user:
        user = User(
            name="Priya Patel",
            email="passenger2@example.com",
            hashed_password=hash_password("PassengerPass123!"),
            role=UserRole.PASSENGER,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


@pytest.fixture
def second_passenger_headers(second_passenger_user: User) -> dict:
    token_dict = create_access_token(
        user_id=second_passenger_user.id,
        email=second_passenger_user.email,
        role=second_passenger_user.role.value,
    )
    return {"Authorization": f"Bearer {token_dict['token']}"}


@pytest.fixture
def sample_stations(session: Session) -> dict:
    """Fixture creating standard sample stations."""
    data = [
        {"code": "NDLS", "name": "New Delhi", "city": "New Delhi"},
        {"code": "GZB", "name": "Ghaziabad", "city": "Ghaziabad"},
        {"code": "ALIG", "name": "Aligarh", "city": "Aligarh"},
        {"code": "CNB", "name": "Kanpur Central", "city": "Kanpur"},
        {"code": "LKO", "name": "Lucknow", "city": "Lucknow"},
    ]
    stations = {}
    for item in data:
        st = session.exec(select(Station).where(Station.station_code == item["code"])).first()
        if not st:
            st = Station(
                station_code=item["code"],
                name=item["name"],
                city=item["city"],
                is_active=True,
            )
            session.add(st)
            session.commit()
            session.refresh(st)
        stations[item["code"]] = st
    return stations


@pytest.fixture
def sample_train(session: Session, sample_stations: dict) -> Train:
    """Fixture creating a 5-stop train with total_seats=5 for testing."""
    train = session.exec(select(Train).where(Train.train_number == "12004")).first()
    if not train:
        train = Train(
            train_number="12004",
            name="Lucknow Shatabdi",
            total_seats=5,
            is_active=True,
        )
        session.add(train)
        session.commit()
        session.refresh(train)

        stops = [
            {"code": "NDLS", "order": 1, "arr": None, "dep": "06:10", "fare": 0.0},
            {"code": "GZB", "order": 2, "arr": "06:48", "dep": "06:50", "fare": 65.0},
            {"code": "ALIG", "order": 3, "arr": "07:50", "dep": "07:52", "fare": 180.0},
            {"code": "CNB", "order": 4, "arr": "11:20", "dep": "11:25", "fare": 650.0},
            {"code": "LKO", "order": 5, "arr": "12:40", "dep": None, "fare": 820.0},
        ]
        for s in stops:
            station = sample_stations[s["code"]]
            route_stop = RouteStop(
                train_id=train.id,
                station_id=station.id,
                stop_order=s["order"],
                arrival_time=s["arr"],
                departure_time=s["dep"],
                fare_from_origin=s["fare"],
            )
            session.add(route_stop)
        session.commit()
        session.refresh(train)
    return train
