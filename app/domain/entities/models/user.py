from dataclasses import dataclass

from app.domain.entities.models.base_model import BaseModel


@dataclass
class User(BaseModel):
    id: str
    name: str
    email: str
    password: str
