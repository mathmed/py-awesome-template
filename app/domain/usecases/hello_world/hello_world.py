from app.domain.contracts.usecase import InputData, Usecase


class HelloWorldParams(InputData):
    name: str


class HelloWorldResponse(InputData):
    message: str


class HelloWorld(Usecase):
    def execute(self, params: HelloWorldParams) -> HelloWorldResponse:
        return HelloWorldResponse(message=f"Hello {params.name}!")
