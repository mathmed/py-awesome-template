
from fastapi import APIRouter, Path

from app.domain.usecases.hello_world.hello_world import HelloWorld, HelloWorldParams

router = APIRouter()


@router.get("/example")
async def example_route(name: str = Path(...)):
    return HelloWorld().execute(HelloWorldParams(
        name=name
    ))
