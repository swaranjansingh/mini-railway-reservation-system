from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RouteStopCreateRequest(BaseModel):
    station_id: int = Field(..., description="ID of an existing station")
    stop_order: int = Field(..., ge=1, description="Sequential order of stop (1, 2, 3...)")
    arrival_time: Optional[str] = Field(default=None, description="Arrival time HH:MM")
    departure_time: Optional[str] = Field(default=None, description="Departure time HH:MM")
    fare_from_origin: float = Field(default=0.0, ge=0.0, description="Cumulative fare from first stop in INR")


class RouteStopUpdateRequest(BaseModel):
    arrival_time: Optional[str] = None
    departure_time: Optional[str] = None
    fare_from_origin: Optional[float] = Field(default=None, ge=0.0)


class RouteStopResponse(BaseModel):
    id: int
    train_id: int
    station_id: int
    station_code: str
    station_name: str
    stop_order: int
    arrival_time: Optional[str]
    departure_time: Optional[str]
    fare_from_origin: float

    model_config = ConfigDict(from_attributes=True)


class TrainCreateRequest(BaseModel):
    train_number: str = Field(..., min_length=3, max_length=20, description="Unique train number, e.g. 12004")
    name: str = Field(..., min_length=3, max_length=100, description="Train name, e.g. Lucknow Shatabdi")
    total_seats: int = Field(..., gt=0, description="Total physical passenger seats")
    stops: Optional[List[RouteStopCreateRequest]] = Field(default=None, description="Initial route stops")

    @field_validator("train_number")
    @classmethod
    def normalize_train_number(cls, v: str) -> str:
        return v.strip().upper()


class TrainUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    total_seats: Optional[int] = Field(default=None, gt=0)
    is_active: Optional[bool] = None


class TrainResponse(BaseModel):
    id: int
    train_number: str
    name: str
    total_seats: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    stops: List[RouteStopResponse] = []

    model_config = ConfigDict(from_attributes=True)


class TrainSearchResponse(BaseModel):
    train_id: int
    train_number: str
    train_name: str
    journey_date: date
    source_station_code: str
    source_station_name: str
    destination_station_code: str
    destination_station_name: str
    departure_time: Optional[str]
    arrival_time: Optional[str]
    fare: float
    total_seats: int
    available_seats: int


class TrainAvailabilityResponse(BaseModel):
    train_id: int
    train_number: str
    train_name: str
    journey_date: date
    source_station_code: str
    destination_station_code: str
    total_seats: int
    booked_seats: int
    available_seats: int
