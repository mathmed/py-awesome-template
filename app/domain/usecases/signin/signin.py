from typing import Any, Optional

from app.domain.contracts.usecase import Usecase


class Signin(Usecase):

    def execute(self, *args: Any | None) -> Any:
        return ''
