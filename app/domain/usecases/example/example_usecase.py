from app.domain.contracts.example_database_contract import ExampleDatabaseContract
from app.domain.contracts.usecase import InputData, Usecase
from app.domain.entities.models.example_model import ExampleModel


class ExampleUsecaseParams(InputData):
    field1: str


class ExampleUsecaseResponse(InputData):
    message: str


class ExampleUsecase(Usecase):

    def __init__(
        self,
        database: ExampleDatabaseContract
    ):
        self.database = database

    def execute(self, params: ExampleUsecaseParams) -> ExampleUsecaseResponse:
        model = self.database.insert(
            ExampleModel(
                field1=params.field1,
            )
        )
        return ExampleUsecaseResponse(message=f"Model inserted! {model.__dict__}")
