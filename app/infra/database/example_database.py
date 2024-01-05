from app.domain.contracts.example_database_contract import ExampleDatabaseContract
from app.domain.entities.models.base_model import BaseModel


class ExampleDatabase(ExampleDatabaseContract):
    """
        This class is an example of a database implementation that implements the ExampleDatabaseContract
    """

    def insert(self, model: BaseModel) -> BaseModel:
        print(f'Inserted! {model}')
        return model
