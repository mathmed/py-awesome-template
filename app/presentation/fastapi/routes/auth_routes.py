
from faker import Faker
from fastapi import APIRouter

from app.domain.usecases.signin import Signin
from app.presentation.factories.usecases_factories import signin_factory

router = APIRouter()


@router.get("/signin")
async def signin():
    faker = Faker()
    return signin_factory().execute(Signin())
