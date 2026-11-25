from typing import Optional, TYPE_CHECKING
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.train import Train
    from app.models.station import Station


class RouteStop(SQLModel, table=True):
    __tablename__ = "route_stops"
    __table_args__ = (
        UniqueConstraint("train_id", "stop_order", name="uq_train_stop_order"),
        UniqueConstraint("train_id", "station_id", name="uq_train_station"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    train_id: int = Field(foreign_key="trains.id", index=True, nullable=False)
    station_id: int = Field(foreign_key="stations.id", index=True, nullable=False)
    stop_order: int = Field(ge=1, nullable=False)
    arrival_time: Optional[str] = Field(default=None, nullable=True)  # Format: "HH:MM"
    departure_time: Optional[str] = Field(default=None, nullable=True)  # Format: "HH:MM"
    fare_from_origin: float = Field(default=0.0, ge=0.0, nullable=False)

    train: Optional["Train"] = Relationship(back_populates="stops")
    station: Optional["Station"] = Relationship(back_populates="route_stops")
