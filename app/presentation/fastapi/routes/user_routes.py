
from http import HTTPStatus

from fastapi import APIRouter, Request, Response

from app.domain.usecases.users.create import CreateUserParams
from app.presentation.factories.usecases_factories import create_user_factory

router = APIRouter(prefix="/users")


@router.post("")
async def create_user(request: Request, response: Response, body: CreateUserParams):
    result = create_user_factory().execute(body)
    if result.success:
        response.status_code = HTTPStatus.CREATED
        return result.data
    response.status_code = HTTPStatus.BAD_REQUEST
    return {"error": result.errorMessage}
