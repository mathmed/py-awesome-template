from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel

NOT_IMPLEMENTED_ERROR = 'This contract method must be implemented'


class BaseClassConfig:
    populate_by_name = True


class InputData(BaseModel):
    class Config(BaseClassConfig):
        pass


class Usecase(ABC):
    @abstractmethod
    def execute(self, *args: Optional[Any]) -> Any:
        """
            Only public method of a usecase. This method will be called by the presentation layer.
        """
        raise NotImplementedError(NOT_IMPLEMENTED_ERROR)
