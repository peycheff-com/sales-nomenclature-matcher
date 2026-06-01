from __future__ import annotations

import json
import logging
import sys

from matcher.logging_config import JSONFormatter, request_id_var, setup_logging


def test_json_formatter_outputs_structured_log_without_request_id():
    record = logging.LogRecord(
        name="matcher.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )

    payload = json.loads(JSONFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "matcher.test"
    assert payload["message"] == "hello world"
    assert "timestamp" in payload
    assert "request_id" not in payload


def test_json_formatter_includes_request_id_and_exception():
    token = request_id_var.set("req-123")
    try:
        try:
            raise ValueError("bad")
        except ValueError:
            record = logging.getLogger("matcher.test").makeRecord(
                "matcher.test",
                logging.ERROR,
                __file__,
                20,
                "failed",
                (),
                exc_info=sys.exc_info(),
            )

        payload = json.loads(JSONFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert payload["request_id"] == "req-123"
    assert payload["message"] == "failed"
    assert "ValueError: bad" in payload["exception"]


def test_setup_logging_configures_root_and_quiets_noisy_loggers():
    setup_logging("DEBUG")

    root = logging.getLogger()

    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JSONFormatter)
    assert logging.getLogger("uvicorn.access").level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING


def test_setup_logging_falls_back_to_info_for_unknown_level():
    setup_logging("not-a-level")

    assert logging.getLogger().level == logging.INFO
