from abc import ABC, abstractmethod

from app.domain.entities.models.base_model import BaseModel


class ExampleDatabaseContract(ABC):
    @abstractmethod
    def insert(self, model: BaseModel) -> BaseModel: ...
