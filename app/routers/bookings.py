from typing import List
from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from app.database import get_session
from app.models.user import User
from app.models.booking import Booking
from app.schemas.booking import (
    BookingCreateRequest,
    BookingResponse,
    BookingCancelResponse,
)
from app.security.dependencies import get_current_user
from app.services.booking_service import BookingService

router = APIRouter(prefix="/api/bookings", tags=["Bookings & Ticketing"])


@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book a train ticket and reserve a seat",
)
def book_ticket(
    req: BookingCreateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BookingResponse:
    booking = BookingService.book_ticket(session, current_user, req)
    return BookingService.format_booking_response(session, booking)


@router.get(
    "/me",
    response_model=List[BookingResponse],
    summary="List all bookings made by the authenticated user",
)
def get_my_bookings(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> List[BookingResponse]:
    bookings = session.exec(
        select(Booking)
        .where(Booking.user_id == current_user.id)
        .order_by(Booking.created_at.desc())
    ).all()
    return [BookingService.format_booking_response(session, b) for b in bookings]


@router.get(
    "/{pnr}",
    response_model=BookingResponse,
    summary="Get booking details by PNR (Owner or Admin only)",
)
def get_booking_by_pnr(
    pnr: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BookingResponse:
    booking = BookingService.get_booking_by_pnr(session, current_user, pnr)
    return BookingService.format_booking_response(session, booking)


@router.post(
    "/{pnr}/cancel",
    response_model=BookingCancelResponse,
    summary="Cancel an active booking (Owner or Admin only)",
)
def cancel_booking(
    pnr: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BookingCancelResponse:
    booking = BookingService.cancel_booking(session, current_user, pnr)
    return BookingCancelResponse(
        message="Ticket has been successfully cancelled and seat released.",
        pnr=booking.pnr,
        status=booking.status.value,
        payment_status=booking.payment_status.value,
        cancelled_at=booking.cancelled_at,
    )
