from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel


class TokenBlocklist(SQLModel, table=True):
    __tablename__ = "token_blocklist"

    id: Optional[int] = Field(default=None, primary_key=True)
    jti: str = Field(unique=True, index=True, nullable=False)
    token_type: str = Field(default="access", nullable=False)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    revoked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    expires_at: datetime = Field(nullable=False)
