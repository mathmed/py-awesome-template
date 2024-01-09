

from typing import Any, Dict, Optional, Type

from pymongo import MongoClient

from app.domain.contracts.database_contract import MODEL, DatabaseContract
from app.domain.services.helpers.envs import get_db_database, get_db_host


class MongoDB(DatabaseContract):
    _instance = None
    _client = None
    _db = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._client:
            self._client = MongoClient(f'mongodb://{get_db_host()}:27017/')
            self._db = self._client[get_db_database()]

    def insert(self, model: MODEL) -> MODEL:
        table = self._db[model.__class__.__name__]  # type: ignore
        fields = MongoDB._parse_fields(model)
        table.insert_one(fields)
        return model

    def find_one(self, model: Type[MODEL], by: str, value: Any) -> Optional[MODEL]:
        if by == 'id':
            by = '_id'
        table = self._db[model.__name__]  # type: ignore
        result = table.find_one({by: value})  # type: ignore
        if result:
            return MongoDB._parse_result(result, model)

    @staticmethod
    def _parse_fields(params: MODEL) -> Dict:
        return {k: v for k, v in params.__dict__.items() if k != '_id'}

    @staticmethod
    def _parse_result(result: Dict, model: Type[MODEL]) -> MODEL:
        result['id'] = str(result['_id'])
        del result['_id']
        return model.model_validate(result)  # type: ignore
