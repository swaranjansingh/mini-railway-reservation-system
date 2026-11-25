import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.config import get_settings
from app.models.user import User
from app.models.password_reset import PasswordResetToken
from app.security.password import hash_password, hash_token

settings = get_settings()


class PasswordResetService:
    @staticmethod
    def create_reset_token(session: Session, email: str) -> Optional[str]:
        """
        Generate a cryptographically secure, single-use password reset token.
        Only the SHA-256 hash is persisted in the database.
        Returns the raw token for simulated development delivery, or None if user not found.
        """
        normalized_email = email.strip().lower()
        user = session.exec(
            select(User).where(User.email == normalized_email)
        ).first()

        if not user or not user.is_active:
            # Return None to preserve generic client response without user enumeration
            return None

        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)

        reset_entry = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=now,
        )
        session.add(reset_entry)
        session.commit()
        return raw_token

    @staticmethod
    def reset_password(session: Session, raw_token: str, new_password: str) -> None:
        """
        Validate single-use token, mark it as consumed, and update password hash.
        """
        token_hash = hash_token(raw_token)
        now = datetime.now(timezone.utc)

        token_record = session.exec(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash
            )
        ).first()

        if not token_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid, expired, or previously used password reset token.",
            )

        if token_record.used_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This password reset token has already been used.",
            )

        # Make sure token expiry comparison is timezone-aware
        token_exp = token_record.expires_at
        if token_exp.tzinfo is None:
            token_exp = token_exp.replace(tzinfo=timezone.utc)

        if token_exp < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This password reset token has expired.",
            )

        user = session.get(User, token_record.user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User account associated with this token is invalid or inactive.",
            )

        # Consume the token atomically
        token_record.used_at = now
        session.add(token_record)

        # Update password hash
        user.hashed_password = hash_password(new_password)
        user.updated_at = now
        session.add(user)

        session.commit()
