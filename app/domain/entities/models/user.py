from app.domain.entities.models.base_model import BaseModel
from app.domain.services.helpers.hash import compare


class User(BaseModel):
    id: str
    name: str
    email: str
    password: str

    def verify_password(self, password: str) -> bool:
        return compare(password, self.password)
