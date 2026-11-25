from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Set, Tuple
from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.station import Station
from app.models.train import Train
from app.models.route import RouteStop
from app.models.booking import Booking, BookingStatus
from app.schemas.station import StationCreateRequest, StationUpdateRequest
from app.schemas.train import (
    TrainCreateRequest,
    TrainUpdateRequest,
    RouteStopCreateRequest,
    RouteStopUpdateRequest,
    TrainSearchResponse,
    TrainAvailabilityResponse,
    RouteStopResponse,
    TrainResponse,
)


class TrainService:
    # -------------------------------------------------------------
    # STATIONS MANAGEMENT
    # -------------------------------------------------------------
    @staticmethod
    def create_station(session: Session, req: StationCreateRequest) -> Station:
        code = req.station_code.strip().upper()
        existing = session.exec(
            select(Station).where(Station.station_code == code)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Station with code '{code}' already exists.",
            )

        station = Station(
            station_code=code,
            name=req.name.strip(),
            city=req.city.strip(),
            is_active=True,
        )
        session.add(station)
        session.commit()
        session.refresh(station)
        return station

    @staticmethod
    def get_stations(session: Session, active_only: bool = True) -> List[Station]:
        statement = select(Station)
        if active_only:
            statement = statement.where(Station.is_active == True)
        statement = statement.order_by(Station.station_code.asc())
        return session.exec(statement).all()

    @staticmethod
    def get_station_by_id(session: Session, station_id: int) -> Station:
        station = session.get(Station, station_id)
        if not station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Station with ID {station_id} not found.",
            )
        return station

    @staticmethod
    def update_station(
        session: Session, station_id: int, req: StationUpdateRequest
    ) -> Station:
        station = TrainService.get_station_by_id(session, station_id)
        if req.name is not None:
            station.name = req.name.strip()
        if req.city is not None:
            station.city = req.city.strip()
        if req.is_active is not None:
            station.is_active = req.is_active

        session.add(station)
        session.commit()
        session.refresh(station)
        return station

    # -------------------------------------------------------------
    # TRAINS & ROUTES MANAGEMENT
    # -------------------------------------------------------------
    @staticmethod
    def create_train(session: Session, req: TrainCreateRequest) -> Train:
        number = req.train_number.strip().upper()
        existing = session.exec(
            select(Train).where(Train.train_number == number)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Train with number '{number}' already exists.",
            )

        if req.total_seats <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Total seats must be a positive integer greater than zero.",
            )

        train = Train(
            train_number=number,
            name=req.name.strip(),
            total_seats=req.total_seats,
            is_active=True,
        )
        session.add(train)
        session.flush()  # Flush to obtain train.id for stops

        if req.stops:
            # Validate route ordering and stations
            seen_stations: Set[int] = set()
            seen_orders: Set[int] = set()
            prev_fare = 0.0

            for stop_req in sorted(req.stops, key=lambda s: s.stop_order):
                # Verify station existence
                station = session.get(Station, stop_req.station_id)
                if not station:
                    session.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Station with ID {stop_req.station_id} does not exist.",
                    )

                if stop_req.station_id in seen_stations:
                    session.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Duplicate station ID {stop_req.station_id} in train route.",
                    )
                seen_stations.add(stop_req.station_id)

                if stop_req.stop_order in seen_orders:
                    session.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Duplicate stop order {stop_req.stop_order} in train route.",
                    )
                seen_orders.add(stop_req.stop_order)

                if stop_req.fare_from_origin < prev_fare:
                    session.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Cumulative fare at stop {stop_req.stop_order} ({stop_req.fare_from_origin}) cannot be less than previous stop ({prev_fare}).",
                    )
                prev_fare = stop_req.fare_from_origin

                route_stop = RouteStop(
                    train_id=train.id,
                    station_id=stop_req.station_id,
                    stop_order=stop_req.stop_order,
                    arrival_time=stop_req.arrival_time,
                    departure_time=stop_req.departure_time,
                    fare_from_origin=stop_req.fare_from_origin,
                )
                session.add(route_stop)

        session.commit()
        session.refresh(train)
        return train

    @staticmethod
    def get_trains(session: Session, active_only: bool = False) -> List[Train]:
        statement = select(Train)
        if active_only:
            statement = statement.where(Train.is_active == True)
        statement = statement.order_by(Train.train_number.asc())
        return session.exec(statement).all()

    @staticmethod
    def get_train_by_id(session: Session, train_id: int) -> Train:
        train = session.get(Train, train_id)
        if not train:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Train with ID {train_id} not found.",
            )
        return train

    @staticmethod
    def update_train(
        session: Session, train_id: int, req: TrainUpdateRequest
    ) -> Train:
        train = TrainService.get_train_by_id(session, train_id)

        if req.name is not None:
            train.name = req.name.strip()

        if req.total_seats is not None:
            if req.total_seats <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Total seats must be greater than zero.",
                )
            # Check highest seat allocated in active bookings
            active_bookings = session.exec(
                select(Booking).where(
                    Booking.train_id == train_id,
                    Booking.status == BookingStatus.CONFIRMED,
                )
            ).all()
            if active_bookings:
                max_booked_seat = max(b.seat_number for b in active_bookings)
                if req.total_seats < max_booked_seat:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Cannot reduce capacity to {req.total_seats} because seat {max_booked_seat} is currently reserved in active bookings.",
                    )
            train.total_seats = req.total_seats

        if req.is_active is not None:
            train.is_active = req.is_active

        train.updated_at = datetime.now(timezone.utc)
        session.add(train)
        session.commit()
        session.refresh(train)
        return train

    @staticmethod
    def deactivate_train(session: Session, train_id: int) -> Train:
        train = TrainService.get_train_by_id(session, train_id)
        train.is_active = False
        train.updated_at = datetime.now(timezone.utc)
        session.add(train)
        session.commit()
        session.refresh(train)
        return train

    @staticmethod
    def add_or_update_route_stop(
        session: Session, train_id: int, req: RouteStopCreateRequest
    ) -> RouteStop:
        train = TrainService.get_train_by_id(session, train_id)
        station = TrainService.get_station_by_id(session, req.station_id)

        # Check existing stop for this train at same order or station
        existing_order = session.exec(
            select(RouteStop).where(
                RouteStop.train_id == train_id,
                RouteStop.stop_order == req.stop_order,
            )
        ).first()

        existing_station = session.exec(
            select(RouteStop).where(
                RouteStop.train_id == train_id,
                RouteStop.station_id == req.station_id,
            )
        ).first()

        if existing_station and existing_station.id != (existing_order.id if existing_order else None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Station {station.station_code} is already in the route of train {train.train_number}.",
            )

        target_stop = existing_order or RouteStop(
            train_id=train_id,
            station_id=req.station_id,
            stop_order=req.stop_order,
        )

        target_stop.station_id = req.station_id
        target_stop.stop_order = req.stop_order
        target_stop.arrival_time = req.arrival_time
        target_stop.departure_time = req.departure_time
        target_stop.fare_from_origin = req.fare_from_origin

        session.add(target_stop)
        session.commit()
        session.refresh(target_stop)
        return target_stop

    @staticmethod
    def update_route_stop(
        session: Session,
        train_id: int,
        stop_id: int,
        req: RouteStopUpdateRequest,
    ) -> RouteStop:
        """
        Update arrival time, departure time, or cumulative fare for an existing stop.
        """
        stop = session.get(RouteStop, stop_id)
        if not stop or stop.train_id != train_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Route stop {stop_id} on train {train_id} not found.",
            )
        if req.arrival_time is not None:
            stop.arrival_time = req.arrival_time
        if req.departure_time is not None:
            stop.departure_time = req.departure_time
        if req.fare_from_origin is not None:
            stop.fare_from_origin = req.fare_from_origin

        session.add(stop)
        session.commit()
        session.refresh(stop)
        return stop

    @staticmethod
    def delete_route_stop(session: Session, train_id: int, stop_id: int) -> None:
        """
        Remove a route stop from a train if no confirmed active bookings exist.
        """
        stop = session.get(RouteStop, stop_id)
        if not stop or stop.train_id != train_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Route stop with ID {stop_id} not found on train {train_id}.",
            )

        # Disallow deleting stops if active confirmed bookings exist
        active_bookings = session.exec(
            select(Booking).where(
                Booking.train_id == train_id,
                Booking.status == BookingStatus.CONFIRMED,
            )
        ).first()
        if active_bookings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete route stop while active confirmed bookings exist on this train.",
            )

        session.delete(stop)
        session.commit()

    @staticmethod
    def format_route_stop_response(stop: RouteStop, session: Session) -> RouteStopResponse:
        """
        Format a RouteStop entity into RouteStopResponse with resolved station metadata.
        """
        station = stop.station or session.get(Station, stop.station_id)
        return RouteStopResponse(
            id=stop.id,
            train_id=stop.train_id,
            station_id=stop.station_id,
            station_code=station.station_code if station else "UNKNOWN",
            station_name=station.name if station else "UNKNOWN",
            stop_order=stop.stop_order,
            arrival_time=stop.arrival_time,
            departure_time=stop.departure_time,
            fare_from_origin=stop.fare_from_origin,
        )

    @staticmethod
    def format_train_response(train: Train, session: Session) -> TrainResponse:
        """
        Format a Train entity into TrainResponse with its ordered route timetable.
        """
        stops_res = [
            TrainService.format_route_stop_response(s, session)
            for s in sorted(train.stops, key=lambda x: x.stop_order)
        ]
        return TrainResponse(
            id=train.id,
            train_number=train.train_number,
            name=train.name,
            total_seats=train.total_seats,
            is_active=train.is_active,
            created_at=train.created_at,
            updated_at=train.updated_at,
            stops=stops_res,
        )

    # -------------------------------------------------------------
    # TRAIN SEARCH & INTERVAL-BASED AVAILABILITY
    # -------------------------------------------------------------
    @staticmethod
    def calculate_occupied_seats(
        session: Session,
        train_id: int,
        journey_date: date,
        src_order: int,
        dst_order: int,
    ) -> Set[int]:
        """
        Calculate the set of physical seat numbers occupied by active bookings
        that overlap with the segment [src_order, dst_order).
        Two segments [A, B) and [C, D) overlap iff max(A, C) < min(B, D).
        """
        confirmed_bookings = session.exec(
            select(Booking).where(
                Booking.train_id == train_id,
                Booking.journey_date == journey_date,
                Booking.status == BookingStatus.CONFIRMED,
            )
        ).all()

        occupied: Set[int] = set()
        for b in confirmed_bookings:
            # Check interval overlap
            if max(b.source_stop_order, src_order) < min(b.destination_stop_order, dst_order):
                occupied.add(b.seat_number)

        return occupied

    @staticmethod
    def search_trains(
        session: Session,
        source_code: str,
        destination_code: str,
        journey_date: date,
    ) -> List[TrainSearchResponse]:
        src_code = source_code.strip().upper()
        dst_code = destination_code.strip().upper()

        if src_code == dst_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination stations cannot be identical.",
            )

        src_station = session.exec(
            select(Station).where(Station.station_code == src_code, Station.is_active == True)
        ).first()
        if not src_station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source station '{src_code}' not found or inactive.",
            )

        dst_station = session.exec(
            select(Station).where(Station.station_code == dst_code, Station.is_active == True)
        ).first()
        if not dst_station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination station '{dst_code}' not found or inactive.",
            )

        # Retrieve all active trains
        trains = session.exec(
            select(Train).where(Train.is_active == True)
        ).all()

        results: List[TrainSearchResponse] = []

        for train in trains:
            stops = session.exec(
                select(RouteStop)
                .where(RouteStop.train_id == train.id)
                .order_by(RouteStop.stop_order.asc())
            ).all()

            src_stop: Optional[RouteStop] = None
            dst_stop: Optional[RouteStop] = None

            for s in stops:
                if s.station_id == src_station.id:
                    src_stop = s
                elif s.station_id == dst_station.id:
                    dst_stop = s

            # Verify that both stops exist and source appears strictly BEFORE destination
            if src_stop and dst_stop and src_stop.stop_order < dst_stop.stop_order:
                segment_fare = round(dst_stop.fare_from_origin - src_stop.fare_from_origin, 2)
                if segment_fare < 0:
                    segment_fare = 0.0

                occupied = TrainService.calculate_occupied_seats(
                    session=session,
                    train_id=train.id,
                    journey_date=journey_date,
                    src_order=src_stop.stop_order,
                    dst_order=dst_stop.stop_order,
                )

                available_count = max(0, train.total_seats - len(occupied))

                results.append(
                    TrainSearchResponse(
                        train_id=train.id,
                        train_number=train.train_number,
                        train_name=train.name,
                        journey_date=journey_date,
                        source_station_code=src_station.station_code,
                        source_station_name=src_station.name,
                        destination_station_code=dst_station.station_code,
                        destination_station_name=dst_station.name,
                        departure_time=src_stop.departure_time or src_stop.arrival_time,
                        arrival_time=dst_stop.arrival_time or dst_stop.departure_time,
                        fare=segment_fare,
                        total_seats=train.total_seats,
                        available_seats=available_count,
                    )
                )

        return results

    @staticmethod
    def get_train_availability(
        session: Session,
        train_id: int,
        source_code: str,
        destination_code: str,
        journey_date: date,
    ) -> TrainAvailabilityResponse:
        train = TrainService.get_train_by_id(session, train_id)
        src_code = source_code.strip().upper()
        dst_code = destination_code.strip().upper()

        if src_code == dst_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination stations cannot be identical.",
            )

        src_station = session.exec(
            select(Station).where(Station.station_code == src_code)
        ).first()
        if not src_station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Station '{src_code}' not found.",
            )

        dst_station = session.exec(
            select(Station).where(Station.station_code == dst_code)
        ).first()
        if not dst_station:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Station '{dst_code}' not found.",
            )

        src_stop = session.exec(
            select(RouteStop).where(
                RouteStop.train_id == train.id,
                RouteStop.station_id == src_station.id,
            )
        ).first()

        dst_stop = session.exec(
            select(RouteStop).where(
                RouteStop.train_id == train.id,
                RouteStop.station_id == dst_station.id,
            )
        ).first()

        if not src_stop or not dst_stop or src_stop.stop_order >= dst_stop.stop_order:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Train {train.train_number} does not operate from {src_code} to {dst_code}.",
            )

        occupied = TrainService.calculate_occupied_seats(
            session=session,
            train_id=train.id,
            journey_date=journey_date,
            src_order=src_stop.stop_order,
            dst_order=dst_stop.stop_order,
        )

        booked_count = len(occupied)
        available_count = max(0, train.total_seats - booked_count)

        return TrainAvailabilityResponse(
            train_id=train.id,
            train_number=train.train_number,
            train_name=train.name,
            journey_date=journey_date,
            source_station_code=src_station.station_code,
            destination_station_code=dst_station.station_code,
            total_seats=train.total_seats,
            booked_seats=booked_count,
            available_seats=available_count,
        )
