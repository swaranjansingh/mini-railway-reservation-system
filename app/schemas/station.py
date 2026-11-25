from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StationCreateRequest(BaseModel):
    station_code: str = Field(..., min_length=2, max_length=10, description="Unique station code, e.g. NDLS")
    name: str = Field(..., min_length=2, max_length=100, description="Full station name")
    city: str = Field(..., min_length=2, max_length=100, description="Station city")

    @field_validator("station_code")
    @classmethod
    def normalize_station_code(cls, v: str) -> str:
        return v.strip().upper()


class StationUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    city: Optional[str] = Field(default=None, min_length=2, max_length=100)
    is_active: Optional[bool] = None


class StationResponse(BaseModel):
    id: int
    station_code: str
    name: str
    city: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
