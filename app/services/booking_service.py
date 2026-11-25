import string
import secrets
import threading
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from typing import Set
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, IntegrityError
from sqlmodel import Session, select

from app.models.user import User, UserRole
from app.models.train import Train
from app.models.station import Station
from app.models.route import RouteStop
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.schemas.booking import BookingCreateRequest, BookingResponse

# Reentrant lock to serialize write/seat-allocation transactions for SQLite within the process.
# Cross-process concurrency is coordinated at the database level via SQLite BEGIN IMMEDIATE.
_booking_lock = threading.RLock()

# Centralized Indian Railway operating timezone (Asia/Kolkata / IST)
RAILWAY_TIMEZONE = ZoneInfo("Asia/Kolkata")


def get_railway_operating_date() -> date:
    """
    Return the current calendar date according to the Indian Railway operating timezone (Asia/Kolkata).
    Decouples journey-date validation from the host machine or container system timezone.
    """
    return datetime.now(RAILWAY_TIMEZONE).date()


def _is_transient_sqlite_error(exc: Exception) -> bool:
    """
    Determine if an exception represents a transient SQLite locking contention error
    ('database is locked', 'table is locked', or 'busy').
    Non-transient errors (e.g., schema or disk errors) return False.
    """
    err_str = f"{str(getattr(exc, 'orig', ''))} {str(exc)}".lower()
    return any(marker in err_str for marker in ("database is locked", "table is locked", "busy"))



class BookingService:
    @staticmethod
    def generate_pnr() -> str:
        """
        Generate a cryptographically secure 10-character PNR string.
        Format: PNR + 7 random uppercase alphanumeric characters.
        """
        charset = string.ascii_uppercase + string.digits
        random_chars = "".join(secrets.choice(charset) for _ in range(7))
        return f"PNR{random_chars}"

    @staticmethod
    def book_ticket(
        session: Session,
        user: User,
        req: BookingCreateRequest,
    ) -> Booking:
        """
        Atomically reserve a seat, allocate PNR, and create a confirmed booking.
        Handles intermediate station journeys, non-overlapping seat reuse,
        and write contention prevention.
        """
        # Timezone policy: Journey dates represent calendar dates of Indian Railway operations (Asia/Kolkata).
        # We compare the journey date against the centralized operating calendar date rather than
        # host-local or UTC date, preventing boundary discrepancies regardless of host machine timezone.
        today = get_railway_operating_date()
        if req.journey_date < today:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot book tickets for past dates.",
            )

        train = session.get(Train, req.train_id)
        if not train:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Train with ID {req.train_id} not found.",
            )

        if not train.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Train {train.train_number} is currently inactive and not accepting reservations.",
            )

        src_station = None
        if req.source_station_id:
            src_station = session.get(Station, req.source_station_id)
        elif req.source_station_code:
            code = req.source_station_code.strip().upper()
            src_station = session.exec(
                select(Station).where(Station.station_code == code)
            ).first()

        if not src_station or not src_station.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Valid active source station must be specified by code or ID.",
            )

        dst_station = None
        if req.destination_station_id:
            dst_station = session.get(Station, req.destination_station_id)
        elif req.destination_station_code:
            code = req.destination_station_code.strip().upper()
            dst_station = session.exec(
                select(Station).where(Station.station_code == code)
            ).first()

        if not dst_station or not dst_station.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Valid active destination station must be specified by code or ID.",
            )

        if src_station.id == dst_station.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination stations cannot be identical.",
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
                detail=f"Train {train.train_number} does not operate from {src_station.station_code} to {dst_station.station_code}.",
            )

        fare = round(dst_stop.fare_from_origin - src_stop.fare_from_origin, 2)
        if fare < 0:
            fare = 0.0

        src_order = src_stop.stop_order
        dst_order = dst_stop.stop_order

        # SQLite transaction coordination:
        # In default deferred mode, SQLite starts transactions in read mode, risking upgrade deadlocks.
        # BEGIN IMMEDIATE acquires a reserved write lock immediately before querying seat availability.
        # Thread reentrant lock (_booking_lock) prevents intra-process thread contention.
        max_retries = 5
        for attempt in range(max_retries):
            try:
                with _booking_lock:
                    try:
                        session.exec(text("BEGIN IMMEDIATE"))
                    except OperationalError as lock_err:
                        if _is_transient_sqlite_error(lock_err):
                            raise
                        if "cannot start a transaction within a transaction" not in str(lock_err).lower():
                            raise
                    except Exception:
                        pass

                    active_bookings = session.exec(
                        select(Booking).where(
                            Booking.train_id == train.id,
                            Booking.journey_date == req.journey_date,
                            Booking.status == BookingStatus.CONFIRMED,
                        )
                    ).all()

                    # Half-open interval overlap: [A, B) and [C, D) conflict iff max(A, C) < min(B, D).
                    # Non-overlapping segments (e.g., [1, 2) and [2, 4)) reuse the same physical seat.
                    occupied_seats: Set[int] = set()
                    for b in active_bookings:
                        if max(b.source_stop_order, src_order) < min(b.destination_stop_order, dst_order):
                            occupied_seats.add(b.seat_number)

                    all_seats = set(range(1, train.total_seats + 1))
                    available_seats = sorted(list(all_seats - occupied_seats))

                    if not available_seats:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="No seats available for this train on the selected travel segment and date.",
                        )

                    chosen_seat = available_seats[0]


                    # Generate a unique PNR with bounded retry
                    pnr = None
                    for _ in range(5):
                        candidate_pnr = BookingService.generate_pnr()
                        existing_pnr = session.exec(
                            select(Booking).where(Booking.pnr == candidate_pnr)
                        ).first()
                        if not existing_pnr:
                            pnr = candidate_pnr
                            break

                    if not pnr:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Unable to generate unique PNR. Please retry.",
                        )

                    booking = Booking(
                        pnr=pnr,
                        user_id=user.id,
                        train_id=train.id,
                        journey_date=req.journey_date,
                        seat_number=chosen_seat,
                        source_station_id=src_station.id,
                        destination_station_id=dst_station.id,
                        source_stop_order=src_order,
                        destination_stop_order=dst_order,
                        fare=fare,
                        status=BookingStatus.CONFIRMED,
                        payment_status=PaymentStatus.PAID,
                        created_at=datetime.now(timezone.utc),
                    )

                    session.add(booking)
                    session.commit()
                    session.refresh(booking)
                    return booking

            except (OperationalError, IntegrityError) as e:
                session.rollback()
                if isinstance(e, OperationalError) and not _is_transient_sqlite_error(e):
                    raise
                if attempt == max_retries - 1:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="High reservation concurrency encountered. Please try again.",
                    )
                time.sleep(0.05 * (attempt + 1))

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred during ticket reservation.",
        )

    @staticmethod
    def get_booking_by_pnr(session: Session, user: User, pnr: str) -> Booking:
        normalized_pnr = pnr.strip().upper()
        booking = session.exec(
            select(Booking).where(Booking.pnr == normalized_pnr)
        ).first()

        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking with PNR '{normalized_pnr}' not found.",
            )

        # Enforce passenger ownership or administrator access
        if booking.user_id != user.id and user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this booking.",
            )

        return booking

    @staticmethod
    def cancel_booking(session: Session, user: User, pnr: str) -> Booking:
        """
        Atomically cancel an existing active booking.
        Releases the physical seat back to availability and marks refund.
        """
        max_retries = 5
        for attempt in range(max_retries):
            try:
                with _booking_lock:
                    try:
                        session.exec(text("BEGIN IMMEDIATE"))
                    except OperationalError as lock_err:
                        if _is_transient_sqlite_error(lock_err):
                            raise
                        if "cannot start a transaction within a transaction" not in str(lock_err).lower():
                            raise
                    except Exception:
                        pass

                    booking = BookingService.get_booking_by_pnr(session, user, pnr)

                    if booking.status == BookingStatus.CANCELLED:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Booking with PNR '{booking.pnr}' has already been cancelled.",
                        )

                    now = datetime.now(timezone.utc)
                    booking.status = BookingStatus.CANCELLED
                    booking.payment_status = PaymentStatus.REFUNDED
                    booking.cancelled_at = now

                    session.add(booking)
                    session.commit()
                    session.refresh(booking)
                    return booking

            except HTTPException:
                session.rollback()
                raise
            except OperationalError as e:
                session.rollback()
                if not _is_transient_sqlite_error(e):
                    raise
                if attempt == max_retries - 1:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="High cancellation concurrency encountered. Please try again.",
                    )
                time.sleep(0.05 * (attempt + 1))

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred during booking cancellation.",
        )

    @staticmethod
    def format_booking_response(session: Session, booking: Booking) -> BookingResponse:
        """
        Format a Booking entity into a BookingResponse with resolved train and station details.
        """
        train = booking.train or session.get(Train, booking.train_id)
        src_station = booking.source_station or session.get(Station, booking.source_station_id)
        dst_station = booking.destination_station or session.get(Station, booking.destination_station_id)

        return BookingResponse(
            id=booking.id,
            pnr=booking.pnr,
            user_id=booking.user_id,
            train_id=booking.train_id,
            train_number=train.train_number if train else "UNKNOWN",
            train_name=train.name if train else "UNKNOWN",
            journey_date=booking.journey_date,
            seat_number=booking.seat_number,
            source_station_code=src_station.station_code if src_station else "UNKNOWN",
            source_station_name=src_station.name if src_station else "UNKNOWN",
            destination_station_code=dst_station.station_code if dst_station else "UNKNOWN",
            destination_station_name=dst_station.name if dst_station else "UNKNOWN",
            source_stop_order=booking.source_stop_order,
            destination_stop_order=booking.destination_stop_order,
            fare=booking.fare,
            status=booking.status.value,
            payment_status=booking.payment_status.value,
            created_at=booking.created_at,
            cancelled_at=booking.cancelled_at,
        )

