

from abc import ABC, abstractmethod
from typing import Any, Optional


class JWTContract(ABC):
    @abstractmethod
    def encode(self, payload: Any, secret: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def decode(self, text: str, secret: str, verify_exp: Optional[bool] = True) -> Optional[Any]:
        raise NotImplementedError
