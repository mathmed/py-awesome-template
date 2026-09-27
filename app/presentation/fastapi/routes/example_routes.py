from fastapi import APIRouter

from app.domain.usecases.example.create_example_usecase import (
    CreateExampleParams,
    CreateExampleResponse,
)
from app.presentation.factories.create_example_factory import create_example_factory

router = APIRouter()


@router.get("/example")
async def example_route(field1: str = "example") -> CreateExampleResponse:
    return create_example_factory().execute(CreateExampleParams(field1=field1))
