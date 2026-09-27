from app.domain.contracts.example_database_contract import ExampleDatabaseContract
from app.domain.contracts.usecase import InputData, Usecase
from app.domain.entities.models.example_model import ExampleModel


class CreateExampleParams(InputData):
    field1: str


class CreateExampleResponse(InputData):
    message: str


class CreateExampleUsecase(Usecase[CreateExampleParams, CreateExampleResponse]):
    def __init__(self, database: ExampleDatabaseContract):
        self.database = database

    def execute(self, params: CreateExampleParams) -> CreateExampleResponse:
        model = self.database.insert(
            ExampleModel(
                field1=params.field1,
            )
        )
        return CreateExampleResponse(message=f"Model inserted! {model.__dict__}")
