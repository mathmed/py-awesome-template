from unittest.mock import MagicMock, create_autospec

from faker import Faker
from pytest import fixture

from app.domain.contracts.example_database_contract import ExampleDatabaseContract
from app.domain.entities.models.example_model import ExampleModel
from app.domain.usecases.example.example_usecase import ExampleUsecase, ExampleUsecaseParams


@fixture
def database() -> MagicMock:
    return create_autospec(ExampleDatabaseContract)


@fixture
def sut(database: MagicMock) -> ExampleUsecase:
    return ExampleUsecase(database=database)


@fixture
def params(faker: Faker) -> ExampleUsecaseParams:
    return ExampleUsecaseParams(field1=faker.word())


def test_should_insert_model_and_return_message(
    sut: ExampleUsecase, database: MagicMock, params: ExampleUsecaseParams, faker: Faker
) -> None:
    database.insert.return_value = ExampleModel(field1=faker.word())
    response = sut.execute(params)
    database.insert.assert_called_once_with(ExampleModel(field1=params.field1))
    assert response.message == f"Model inserted! {database.insert.return_value.__dict__}"
