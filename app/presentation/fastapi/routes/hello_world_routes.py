
from fastapi import APIRouter, Path

from app.domain.usecases.hello_world.hello_world import HelloWorld, HelloWorldParams

router = APIRouter()


@router.get("/hello-world/{name}")
async def hello_world(name: str = Path(...)):
    return HelloWorld().execute(HelloWorldParams(
        name=name
    ))
