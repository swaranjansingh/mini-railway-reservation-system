from typing import List
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.schemas.station import StationResponse
from app.services.train_service import TrainService

router = APIRouter(prefix="/api/stations", tags=["Stations"])


@router.get("", response_model=List[StationResponse], summary="List all active stations")
def list_stations(
    session: Session = Depends(get_session),
) -> List[StationResponse]:
    stations = TrainService.get_stations(session, active_only=True)
    return [StationResponse.model_validate(s) for s in stations]


@router.get("/{station_id}", response_model=StationResponse, summary="Get station details by ID")
def get_station(
    station_id: int,
    session: Session = Depends(get_session),
) -> StationResponse:
    station = TrainService.get_station_by_id(session, station_id)
    return StationResponse.model_validate(station)
