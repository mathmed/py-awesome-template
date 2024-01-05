

from abc import ABC, abstractmethod

from app.domain.entities.models.base_model import BaseModel


class ExampleDatabaseContract(ABC):
    """
        This class is an example of a database contract that will be implemented by a database class
    """
    @abstractmethod
    def insert(self, foo: BaseModel) -> BaseModel:
        raise NotImplementedError
