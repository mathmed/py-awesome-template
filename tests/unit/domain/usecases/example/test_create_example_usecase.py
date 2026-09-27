from unittest.mock import MagicMock, create_autospec

from faker import Faker
from pytest import fixture

from app.domain.contracts.example_database_contract import ExampleDatabaseContract
from app.domain.entities.models.example_model import ExampleModel
from app.domain.usecases.example.create_example_usecase import (
    CreateExampleParams,
    CreateExampleUsecase,
)


@fixture
def database() -> MagicMock:
    database: MagicMock = create_autospec(ExampleDatabaseContract)
    return database


@fixture
def sut(database: MagicMock) -> CreateExampleUsecase:
    return CreateExampleUsecase(database=database)


@fixture
def params(faker: Faker) -> CreateExampleParams:
    return CreateExampleParams(field1=faker.word())


def test_should_insert_model_and_return_message(
    sut: CreateExampleUsecase, database: MagicMock, params: CreateExampleParams, faker: Faker
) -> None:
    database.insert.return_value = ExampleModel(field1=faker.word())
    response = sut.execute(params)
    database.insert.assert_called_once_with(ExampleModel(field1=params.field1))
    assert response.message == f"Model inserted! {database.insert.return_value.__dict__}"
