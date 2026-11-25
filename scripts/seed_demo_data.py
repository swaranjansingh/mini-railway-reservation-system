import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlmodel import Session, select

from app.database import engine, init_db
from app.models.station import Station
from app.models.train import Train
from app.models.route import RouteStop


def seed_data() -> None:
    """
    Seed fictional demonstration stations, trains, and routes.
    Ensures idempotency by checking existing records.
    """
    init_db()

    stations_data = [
        {"code": "NDLS", "name": "New Delhi", "city": "New Delhi"},
        {"code": "GZB", "name": "Ghaziabad Junction", "city": "Ghaziabad"},
        {"code": "ALIG", "name": "Aligarh Junction", "city": "Aligarh"},
        {"code": "CNB", "name": "Kanpur Central", "city": "Kanpur"},
        {"code": "LKO", "name": "Lucknow Central", "city": "Lucknow"},
    ]

    with Session(engine) as session:
        print("[*] Seeding fictional stations...")
        station_map = {}
        for s_data in stations_data:
            existing = session.exec(
                select(Station).where(Station.station_code == s_data["code"])
            ).first()
            if not existing:
                station = Station(
                    station_code=s_data["code"],
                    name=s_data["name"],
                    city=s_data["city"],
                    is_active=True,
                )
                session.add(station)
                session.flush()
                station_map[s_data["code"]] = station
                print(f"    [+] Created station {s_data['code']} - {s_data['name']}")
            else:
                station_map[s_data["code"]] = existing
                print(f"    [i] Station {s_data['code']} already exists")

        print("[*] Seeding fictional trains and routes...")

        trains_data = [
            {
                "number": "12004",
                "name": "Lucknow Shatabdi Express",
                "total_seats": 5,  # Compact capacity for easy full-train demonstration
                "stops": [
                    {"code": "NDLS", "order": 1, "arr": None, "dep": "06:10", "fare": 0.0},
                    {"code": "GZB", "order": 2, "arr": "06:48", "dep": "06:50", "fare": 65.0},
                    {"code": "ALIG", "order": 3, "arr": "07:50", "dep": "07:52", "fare": 180.0},
                    {"code": "CNB", "order": 4, "arr": "11:20", "dep": "11:25", "fare": 650.0},
                    {"code": "LKO", "order": 5, "arr": "12:40", "dep": None, "fare": 820.0},
                ],
            },
            {
                "number": "12418",
                "name": "Prayagraj Express",
                "total_seats": 50,
                "stops": [
                    {"code": "NDLS", "order": 1, "arr": None, "dep": "22:10", "fare": 0.0},
                    {"code": "ALIG", "order": 2, "arr": "23:55", "dep": "23:57", "fare": 210.0},
                    {"code": "CNB", "order": 3, "arr": "03:50", "dep": "03:55", "fare": 720.0},
                ],
            },
            {
                "number": "12002",
                "name": "Bhopal Shatabdi Express",
                "total_seats": 40,
                "stops": [
                    {"code": "NDLS", "order": 1, "arr": None, "dep": "06:00", "fare": 0.0},
                    {"code": "GZB", "order": 2, "arr": "06:30", "dep": "06:32", "fare": 70.0},
                    {"code": "ALIG", "order": 3, "arr": "07:30", "dep": "07:32", "fare": 195.0},
                ],
            },
        ]

        for t_data in trains_data:
            existing_train = session.exec(
                select(Train).where(Train.train_number == t_data["number"])
            ).first()

            if not existing_train:
                train = Train(
                    train_number=t_data["number"],
                    name=t_data["name"],
                    total_seats=t_data["total_seats"],
                    is_active=True,
                )
                session.add(train)
                session.flush()

                for stop in t_data["stops"]:
                    station = station_map[stop["code"]]
                    route_stop = RouteStop(
                        train_id=train.id,
                        station_id=station.id,
                        stop_order=stop["order"],
                        arrival_time=stop["arr"],
                        departure_time=stop["dep"],
                        fare_from_origin=stop["fare"],
                    )
                    session.add(route_stop)

                print(f"    [+] Created train {t_data['number']} ({t_data['name']}) with {len(t_data['stops'])} stops")
            else:
                print(f"    [i] Train {t_data['number']} already exists")

        session.commit()
        print("[✓] Demonstration dataset successfully seeded!")


if __name__ == "__main__":
    seed_data()
