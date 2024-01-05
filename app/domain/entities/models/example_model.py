from dataclasses import dataclass

from app.domain.entities.models.base_model import BaseModel


@dataclass
class ExampleModel(BaseModel):
    field1: str
