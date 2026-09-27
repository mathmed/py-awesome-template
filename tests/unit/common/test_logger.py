import json
import logging
import sys

from app.common.logger import JsonFormatter, configure_logging
from app.common.settings import Environment, Settings


def make_record(exc_info: bool = False) -> logging.LogRecord:
    try:
        raise ValueError("boom")
    except ValueError:
        return logging.LogRecord(
            "some.logger",
            logging.ERROR,
            __file__,
            1,
            "hello %s",
            ("world",),
            exc_info=sys.exc_info() if exc_info else None,
        )


def test_should_serialize_record_as_json() -> None:
    payload = json.loads(JsonFormatter().format(make_record()))
    assert payload["level"] == "ERROR"
    assert payload["logger"] == "some.logger"
    assert payload["message"] == "hello world"
    assert "exception" not in payload


def test_should_include_exception_in_json() -> None:
    payload = json.loads(JsonFormatter().format(make_record(exc_info=True)))
    assert "ValueError: boom" in payload["exception"]


def test_should_use_json_formatter_in_production() -> None:
    configure_logging(Settings(env=Environment.PRODUCTION))
    assert isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)
