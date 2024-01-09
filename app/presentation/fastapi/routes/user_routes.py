
from http import HTTPStatus

from fastapi import APIRouter, Request, Response

from app.domain.usecases.users.create import CreateUserParams, CreateUserResponseData
from app.presentation.factories.usecases_factories import create_user_factory

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.post("", status_code=HTTPStatus.CREATED, responses={
    # This FastAPI feature generates the OpenAPI schema automatically
    HTTPStatus.CREATED.value: {"description": "Success", "model": CreateUserResponseData},
    HTTPStatus.BAD_REQUEST.value: {"description": "Validation error"},
})
async def create_user(request: Request, response: Response, body: CreateUserParams):
    result = create_user_factory().execute(body)
    if result.success:
        response.status_code = HTTPStatus.CREATED
        return result.data
    response.status_code = HTTPStatus.BAD_REQUEST
    return {"error": result.errorMessage}
