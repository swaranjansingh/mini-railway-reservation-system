from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.route import RouteStop
    from app.models.booking import Booking


class Train(SQLModel, table=True):
    __tablename__ = "trains"

    id: Optional[int] = Field(default=None, primary_key=True)
    train_number: str = Field(unique=True, index=True, nullable=False)
    name: str = Field(nullable=False)
    total_seats: int = Field(gt=0, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    stops: List["RouteStop"] = Relationship(back_populates="train", cascade_delete=True)
    bookings: List["Booking"] = Relationship(back_populates="train")
