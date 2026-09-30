from fastapi import APIRouter

from app.domain.usecases.health.check_readiness_usecase import (
    CheckReadinessParams,
    CheckReadinessResponse,
)
from app.presentation.factories.check_readiness_factory import check_readiness_factory

router = APIRouter()


@router.get("/ready")
async def ready_route() -> CheckReadinessResponse:
    return check_readiness_factory().execute(CheckReadinessParams())
