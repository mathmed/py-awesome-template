from fastapi import APIRouter

from app.domain.usecases.example.example_usecase import (
    ExampleUsecaseParams,
    ExampleUsecaseResponse,
)
from app.presentation.factories.example_factory import example_factory

router = APIRouter()


@router.get("/example")
async def example_route(field1: str = "example") -> ExampleUsecaseResponse:
    return example_factory().execute(ExampleUsecaseParams(field1=field1))
