from typing import List, Optional, TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.route import RouteStop


class Station(SQLModel, table=True):
    __tablename__ = "stations"

    id: Optional[int] = Field(default=None, primary_key=True)
    station_code: str = Field(unique=True, index=True, nullable=False)
    name: str = Field(nullable=False)
    city: str = Field(nullable=False)
    is_active: bool = Field(default=True, nullable=False)

    route_stops: List["RouteStop"] = Relationship(back_populates="station")
