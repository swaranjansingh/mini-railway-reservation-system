from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.train import Train
    from app.models.station import Station


class BookingStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, Enum):
    PAID = "PAID"
    REFUNDED = "REFUNDED"


class Booking(SQLModel, table=True):
    __tablename__ = "bookings"

    id: Optional[int] = Field(default=None, primary_key=True)
    pnr: str = Field(unique=True, index=True, nullable=False)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    train_id: int = Field(foreign_key="trains.id", index=True, nullable=False)
    journey_date: date = Field(index=True, nullable=False)
    seat_number: int = Field(ge=1, nullable=False)
    source_station_id: int = Field(foreign_key="stations.id", nullable=False)
    destination_station_id: int = Field(foreign_key="stations.id", nullable=False)
    source_stop_order: int = Field(ge=1, nullable=False)
    destination_stop_order: int = Field(ge=1, nullable=False)
    fare: float = Field(ge=0.0, nullable=False)
    status: BookingStatus = Field(default=BookingStatus.CONFIRMED, nullable=False)
    payment_status: PaymentStatus = Field(default=PaymentStatus.PAID, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    cancelled_at: Optional[datetime] = Field(default=None, nullable=True)

    user: Optional["User"] = Relationship(back_populates="bookings")
    train: Optional["Train"] = Relationship(back_populates="bookings")
    source_station: Optional["Station"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Booking.source_station_id]"}
    )
    destination_station: Optional["Station"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Booking.destination_station_id]"}
    )
