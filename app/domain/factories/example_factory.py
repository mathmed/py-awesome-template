

from app.domain.usecases.example.example_usecase import ExampleUsecase
from app.infra.database.example_database import ExampleDatabase


def example_factory() -> ExampleUsecase:
    """
        This function is an example of a factory that will create an instance of ExampleUsecase.
        Here we can inject the dependencies of ExampleUsecase.
    """
    return ExampleUsecase(
        database=ExampleDatabase()
    )
