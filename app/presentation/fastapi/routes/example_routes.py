
from faker import Faker
from fastapi import APIRouter

from app.domain.factories.example_factory import example_factory
from app.domain.usecases.example.example_usecase import ExampleUsecaseParams

router = APIRouter()


@router.get("/example")
async def example_route():
    faker = Faker()
    return example_factory().execute(ExampleUsecaseParams(
        field1=faker.word()
    ))
