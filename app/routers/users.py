from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.models.user import User
from app.models.booking import Booking
from app.schemas.user import UserResponse, UserUpdateRequest
from app.schemas.booking import BookingResponse
from app.security.dependencies import get_current_user
from app.security.password import verify_password, hash_password
from app.services.booking_service import BookingService

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("/me", response_model=UserResponse, summary="Get current user profile")
def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse, summary="Update current user profile")
def update_my_profile(
    req: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserResponse:
    if req.name is not None:
        current_user.name = req.name.strip()

    if req.new_password is not None:
        if not req.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is required to set a new password.",
            )
        if not verify_password(req.current_password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password verification failed.",
            )
        current_user.hashed_password = hash_password(req.new_password)

    current_user.updated_at = datetime.now(timezone.utc)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.get(
    "/me/bookings",
    response_model=List[BookingResponse],
    summary="Get current user's booking history",
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

