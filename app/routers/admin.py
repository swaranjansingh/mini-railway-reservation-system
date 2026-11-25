from typing import List
from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.database import get_session
from app.models.user import User
from app.schemas.station import (
    StationCreateRequest,
    StationUpdateRequest,
    StationResponse,
)
from app.schemas.train import (
    TrainCreateRequest,
    TrainUpdateRequest,
    TrainResponse,
    RouteStopCreateRequest,
    RouteStopResponse,
    RouteStopUpdateRequest,
)
from app.schemas.auth import MessageResponse
from app.security.dependencies import get_current_admin
from app.services.train_service import TrainService

router = APIRouter(prefix="/api/admin", tags=["Admin Railway Management"])


# -------------------------------------------------------------------
# STATIONS MANAGEMENT (ADMIN)
# -------------------------------------------------------------------
@router.post(
    "/stations",
    response_model=StationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new railway station (Admin Only)",
)
def create_station(
    req: StationCreateRequest,
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> StationResponse:
    station = TrainService.create_station(session, req)
    return StationResponse.model_validate(station)


@router.patch(
    "/stations/{station_id}",
    response_model=StationResponse,
    summary="Update railway station details (Admin Only)",
)
def update_station(
    station_id: int,
    req: StationUpdateRequest,
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> StationResponse:
    station = TrainService.update_station(session, station_id, req)
    return StationResponse.model_validate(station)


# -------------------------------------------------------------------
# TRAINS MANAGEMENT (ADMIN)
# -------------------------------------------------------------------
@router.post(
    "/trains",
    response_model=TrainResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new train with route stops (Admin Only)",
)
def create_train(
    req: TrainCreateRequest,
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> TrainResponse:
    train = TrainService.create_train(session, req)
    return TrainService.format_train_response(train, session)


@router.get(
    "/trains",
    response_model=List[TrainResponse],
    summary="List all trains with full route information (Admin Only)",
)
def list_trains(
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> List[TrainResponse]:
    trains = TrainService.get_trains(session, active_only=False)
    return [TrainService.format_train_response(t, session) for t in trains]


@router.patch(
    "/trains/{train_id}",
    response_model=TrainResponse,
    summary="Update train parameters or capacity (Admin Only)",
)
def update_train(
    train_id: int,
    req: TrainUpdateRequest,
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> TrainResponse:
    train = TrainService.update_train(session, train_id, req)
    return TrainService.format_train_response(train, session)


@router.patch(
    "/trains/{train_id}/deactivate",
    response_model=TrainResponse,
    summary="Deactivate a train (Preserves historical bookings) (Admin Only)",
)
def deactivate_train(
    train_id: int,
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> TrainResponse:
    train = TrainService.deactivate_train(session, train_id)
    return TrainService.format_train_response(train, session)


# -------------------------------------------------------------------
# ROUTE STOPS MANAGEMENT (ADMIN)
# -------------------------------------------------------------------
@router.post(
    "/trains/{train_id}/stops",
    response_model=RouteStopResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add or update a route stop on a train (Admin Only)",
)
def add_route_stop(
    train_id: int,
    req: RouteStopCreateRequest,
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> RouteStopResponse:
    stop = TrainService.add_or_update_route_stop(session, train_id, req)
    return TrainService.format_route_stop_response(stop, session)


@router.patch(
    "/trains/{train_id}/stops/{stop_id}",
    response_model=RouteStopResponse,
    summary="Update timings or fare for a route stop (Admin Only)",
)
def update_route_stop(
    train_id: int,
    stop_id: int,
    req: RouteStopUpdateRequest,
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> RouteStopResponse:
    stop = TrainService.update_route_stop(session, train_id, stop_id, req)
    return TrainService.format_route_stop_response(stop, session)


@router.delete(
    "/trains/{train_id}/stops/{stop_id}",
    response_model=MessageResponse,
    summary="Delete a route stop (Admin Only)",
)
def delete_route_stop(
    train_id: int,
    stop_id: int,
    admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session),
) -> MessageResponse:
    TrainService.delete_route_stop(session, train_id, stop_id)
    return MessageResponse(message=f"Route stop {stop_id} deleted successfully.")

