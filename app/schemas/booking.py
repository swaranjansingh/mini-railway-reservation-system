from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class BookingCreateRequest(BaseModel):
    train_id: int = Field(..., description="ID of the train to book")
    journey_date: date = Field(..., description="Date of travel (YYYY-MM-DD)")
    source_station_code: Optional[str] = Field(default=None, description="Starting station code (e.g. NDLS)")
    destination_station_code: Optional[str] = Field(default=None, description="Destination station code (e.g. CNB)")
    source_station_id: Optional[int] = Field(default=None, description="Starting station ID")
    destination_station_id: Optional[int] = Field(default=None, description="Destination station ID")


class BookingResponse(BaseModel):
    id: int
    pnr: str
    user_id: int
    train_id: int
    train_number: str
    train_name: str
    journey_date: date
    seat_number: int
    source_station_code: str
    source_station_name: str
    destination_station_code: str
    destination_station_name: str
    source_stop_order: int
    destination_stop_order: int
    fare: float
    status: str
    payment_status: str
    created_at: datetime
    cancelled_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BookingCancelResponse(BaseModel):
    message: str
    pnr: str
    status: str
    payment_status: str
    cancelled_at: datetime
