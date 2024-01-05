

from unittest.mock import MagicMock, create_autospec

from faker import Faker
from pytest import fixture

from app.domain.contracts.example_database_contract import ExampleDatabaseContract
from app.domain.entities.models.example_model import ExampleModel

from .example_usecase import ExampleUsecase, ExampleUsecaseParams


@fixture
def sut() -> ExampleUsecase:
    return ExampleUsecase(
        database=create_autospec(ExampleDatabaseContract)
    )


@fixture
def params(faker: Faker) -> ExampleUsecaseParams:
    return ExampleUsecaseParams(
        field1=faker.word()
    )


def test_should_return_hello_world(
    sut: ExampleUsecase,
    params: ExampleUsecaseParams,
    faker: Faker
) -> None:
    sut.database.insert = MagicMock(return_value=ExampleModel(field1=faker.word()))
    response = sut.execute(params)
    assert response.message == f"Model inserted! {sut.database.insert.return_value.__dict__}"
