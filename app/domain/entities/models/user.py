from dataclasses import dataclass

from app.domain.entities.models.base_model import BaseModel
from app.domain.services.helpers.hash import compare


@dataclass
class User(BaseModel):
    id: str
    name: str
    email: str
    password: str

    def verify_password(self, password: str) -> bool:
        return compare(password, self.password)
