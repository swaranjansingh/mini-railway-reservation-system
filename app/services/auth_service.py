from datetime import datetime
from typing import Dict, Any
from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.user import User, UserRole
from app.models.token_blocklist import TokenBlocklist
from app.schemas.auth import UserRegisterRequest, UserLoginRequest
from app.security.password import hash_password, verify_password
from app.security.jwt import create_access_token


class AuthService:
    @staticmethod
    def register_user(session: Session, req: UserRegisterRequest) -> User:
        """
        Register a new passenger account.
        Public registration strictly creates PASSENGER role accounts.
        """
        normalized_email = req.email.strip().lower()

        existing = session.exec(
            select(User).where(User.email == normalized_email)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email address already exists.",
            )

        hashed_pwd = hash_password(req.password)
        new_user = User(
            name=req.name.strip(),
            email=normalized_email,
            hashed_password=hashed_pwd,
            role=UserRole.PASSENGER,
            is_active=True,
        )
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        return new_user

    @staticmethod
    def login_user(session: Session, req: UserLoginRequest) -> Dict[str, Any]:
        """
        Authenticate user credentials and return a signed JWT.
        """
        normalized_email = req.email.strip().lower()
        user = session.exec(
            select(User).where(User.email == normalized_email)
        ).first()

        if not user or not verify_password(req.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This account has been deactivated. Please contact support.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token_data = create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role.value,
        )

        return {
            "access_token": token_data["token"],
            "token_type": "bearer",
            "expires_in_seconds": token_data["expires_in_seconds"],
            "role": user.role.value,
        }

    @staticmethod
    def logout_token(
        session: Session,
        jti: str,
        user_id: int,
        exp_datetime: datetime,
    ) -> None:
        """
        Revoke an active JWT on the server side by saving its JTI into the blocklist.
        """
        existing = session.exec(
            select(TokenBlocklist).where(TokenBlocklist.jti == jti)
        ).first()
        if not existing:
            block_entry = TokenBlocklist(
                jti=jti,
                user_id=user_id,
                expires_at=exp_datetime,
            )
            session.add(block_entry)
            session.commit()
