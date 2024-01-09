from traceback import format_exc
from typing import Any, Optional

import jwt

from app.domain.contracts import JWTContract


class JWT(JWTContract):

    def encode(self, payload: Any, secret: str) -> Any:
        return jwt.encode(payload, secret, "HS256")

    def decode(self, text: str, secret: str, verify_exp: Optional[bool] = True) -> Optional[Any]:
        try:
            return jwt.decode(text, secret, algorithms=['HS256'], options={"verify_exp": verify_exp})
        except Exception:
            print(f'Error to decode JWT: {format_exc()}')
        return None

    @staticmethod
    def _prepare_key(key):
        return jwt.utils.force_bytes(key)  # type: ignore


jwt.api_jws._jws_global_obj._algorithms['HS256'].prepare_key = JWT._prepare_key  # type: ignore
