

from abc import ABC, abstractmethod
from typing import Any, Optional, Type, TypeVar

from app.domain.entities.models.base_model import BaseModel

MODEL = TypeVar('M', bound=BaseModel)


class DatabaseContract(ABC):
    @abstractmethod
    def insert(self, model: MODEL) -> MODEL:
        raise NotImplementedError

    @abstractmethod
    def find_one(self, model: Type[MODEL], by: str, value: Any) -> Optional[MODEL]:
        raise NotImplementedError
