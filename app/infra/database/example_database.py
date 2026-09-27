import logging

from app.domain.contracts.example_database_contract import ExampleDatabaseContract
from app.domain.entities.models.base_model import BaseModel

logger = logging.getLogger(__name__)


class ExampleDatabase(ExampleDatabaseContract):
    def insert(self, model: BaseModel) -> BaseModel:
        logger.info("Inserted %s", model)
        return model
