from datetime import datetime, timezone
from typing import Tuple
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlmodel import Session, select

from app.database import get_session
from app.models.user import User, UserRole
from app.models.token_blocklist import TokenBlocklist
from app.security.jwt import decode_access_token

security_scheme = HTTPBearer(auto_error=False)


def get_current_user_and_token(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    session: Session = Depends(get_session),
) -> Tuple[User, str, str, datetime]:
    """
    Extract and validate JWT Bearer token, check revocation blocklist,
    and return (User, raw_token, jti, exp_datetime).
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials
    try:
        payload = decode_access_token(raw_token)
        user_id_str = payload.get("sub")
        jti = payload.get("jti")
        exp_timestamp = payload.get("exp")

        if user_id_str is None or jti is None or exp_timestamp is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload claims.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = int(user_id_str)
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check server-side token revocation blocklist
    blocked = session.exec(
        select(TokenBlocklist).where(TokenBlocklist.jti == jti)
    ).first()
    if blocked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load fresh user record from DB (do NOT rely solely on JWT role claim)
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user, raw_token, jti, exp_datetime


def get_current_user(
    auth_data: Tuple[User, str, str, datetime] = Depends(get_current_user_and_token),
) -> User:
    """Dependency that resolves the active authenticated user."""
    return auth_data[0]


def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency that ensures the authenticated user is an administrator."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to perform this action.",
        )
    return current_user
