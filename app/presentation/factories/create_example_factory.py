from app.domain.usecases.example.create_example_usecase import CreateExampleUsecase
from app.infra.database.example_database import ExampleDatabase


def create_example_factory() -> CreateExampleUsecase:
    return CreateExampleUsecase(database=ExampleDatabase())
