from datetime import datetime
from typing import Tuple
from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.config import get_settings
from app.database import get_session
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    MessageResponse,
)
from app.schemas.user import UserResponse
from app.security.dependencies import get_current_user_and_token
from app.services.auth_service import AuthService
from app.services.password_reset_service import PasswordResetService

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new passenger account",
)
def register(
    req: UserRegisterRequest,
    session: Session = Depends(get_session),
) -> UserResponse:
    user = AuthService.register_user(session, req)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a JWT access token",
)
def login(
    req: UserLoginRequest,
    session: Session = Depends(get_session),
) -> TokenResponse:
    token_dict = AuthService.login_user(session, req)
    return TokenResponse(**token_dict)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Log out and revoke current access token",
)
def logout(
    auth_data: Tuple[User, str, str, datetime] = Depends(get_current_user_and_token),
    session: Session = Depends(get_session),
) -> MessageResponse:
    current_user, raw_token, jti, exp_datetime = auth_data
    AuthService.logout_token(
        session=session,
        jti=jti,
        user_id=current_user.id,
        exp_datetime=exp_datetime,
    )
    return MessageResponse(message="Successfully logged out and session revoked.")


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Request a password reset link/token",
)
def forgot_password(
    req: ForgotPasswordRequest,
    session: Session = Depends(get_session),
) -> ForgotPasswordResponse:
    raw_token = PasswordResetService.create_reset_token(session, req.email)

    # In development, simulate email delivery by returning the token in the response
    dev_token = None
    if settings.ENVIRONMENT != "production" and raw_token:
        dev_token = raw_token

    return ForgotPasswordResponse(
        message="If an active account exists for that email, a password reset link has been dispatched.",
        dev_reset_token=dev_token,
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset password using a valid single-use token",
)
def reset_password(
    req: ResetPasswordRequest,
    session: Session = Depends(get_session),
) -> MessageResponse:
    PasswordResetService.reset_password(session, req.token, req.new_password)
    return MessageResponse(message="Password has been successfully reset. Please log in with your new credentials.")
