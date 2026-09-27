from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict


class InputData(BaseModel):
    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)


class Usecase[Params, Response](ABC):
    @abstractmethod
    def execute(self, params: Params) -> Response:
        """
        Only public method of a usecase. This method will be called by the presentation layer.
        """
        ...
