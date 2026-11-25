from datetime import date
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.database import get_session
from app.schemas.train import (
    TrainResponse,
    TrainSearchResponse,
    TrainAvailabilityResponse,
)
from app.services.train_service import TrainService

router = APIRouter(prefix="/api/trains", tags=["Trains & Search"])


@router.get(
    "/search",
    response_model=List[TrainSearchResponse],
    summary="Search trains between stations for a journey date",
)
def search_trains(
    source_station_code: str = Query(..., description="Origin station code, e.g. NDLS"),
    destination_station_code: str = Query(..., description="Destination station code, e.g. CNB"),
    journey_date: date = Query(..., description="Date of journey (YYYY-MM-DD)"),
    session: Session = Depends(get_session),
) -> List[TrainSearchResponse]:
    return TrainService.search_trains(
        session=session,
        source_code=source_station_code,
        destination_code=destination_station_code,
        journey_date=journey_date,
    )


@router.get(
    "/{train_id}",
    response_model=TrainResponse,
    summary="Get train details and route timetable",
)
def get_train_details(
    train_id: int,
    session: Session = Depends(get_session),
) -> TrainResponse:
    train = TrainService.get_train_by_id(session, train_id)
    return TrainService.format_train_response(train, session)


@router.get(
    "/{train_id}/availability",
    response_model=TrainAvailabilityResponse,
    summary="Check real-time seat availability for a travel segment",
)
def check_seat_availability(
    train_id: int,
    source_station_code: str = Query(..., description="Origin station code, e.g. NDLS"),
    destination_station_code: str = Query(..., description="Destination station code, e.g. CNB"),
    journey_date: date = Query(..., description="Date of journey (YYYY-MM-DD)"),
    session: Session = Depends(get_session),
) -> TrainAvailabilityResponse:
    return TrainService.get_train_availability(
        session=session,
        train_id=train_id,
        source_code=source_station_code,
        destination_code=destination_station_code,
        journey_date=journey_date,
    )
