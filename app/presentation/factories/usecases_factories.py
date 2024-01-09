

from app.domain.usecases.signin import Signin
from app.domain.usecases.users.create import CreateUser
from app.infra.database.mongodb.mongodb import MongoDB


def signin_factory() -> Signin:
    return Signin()


def create_user_factory() -> CreateUser:
    return CreateUser(
        database=MongoDB()
    )
