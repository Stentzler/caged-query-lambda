import importlib
import io
import json
import sys
from types import ModuleType


class FakeLambdaContext:
    function_name = "boilerplate-test"
    function_version = "$LATEST"
    invoked_function_arn = (
        "arn:aws:lambda:us-east-1:123456789012:function:boilerplate-test"
    )
    memory_limit_in_mb = 128
    aws_request_id = "test-request-id"
    log_group_name = "/aws/lambda/boilerplate-test"
    log_stream_name = "2026/01/01/[$LATEST]abcdef"


def load_handler_module(monkeypatch) -> ModuleType:
    monkeypatch.setenv("SOURCE_NAME", "boilerplate-test")
    monkeypatch.setenv("POWERTOOLS_SERVICE_NAME", "boilerplate-test")
    monkeypatch.setenv("POWERTOOLS_LOG_LEVEL", "INFO")
    monkeypatch.setenv("POWERTOOLS_LOG_EVENT", "false")
    sys.modules.pop("handler", None)

    return importlib.import_module("handler")


def test_handler_returns_service_result(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)
    expected = {
        "status": "ok",
        "source": "boilerplate-test",
        "event": {"hello": "world"},
    }

    class FakeService:
        def execute(self, event):
            assert event == {"hello": "world"}
            return expected

    class FakeLogger:
        def __init__(self) -> None:
            self.info_calls = []

        def info(self, message, **context) -> None:
            self.info_calls.append((message, context))

    monkeypatch.setattr(handler_module, "service", FakeService())
    fake_logger = FakeLogger()
    monkeypatch.setattr(handler_module, "logger", fake_logger)

    response = handler_module.handler({"hello": "world"}, FakeLambdaContext())

    assert response is expected
    assert fake_logger.info_calls[-1] == (
        "Finished boilerplate Lambda",
        {"result": expected},
    )


def test_handler_propagates_service_error(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)

    class FailingService:
        def execute(self, event):
            raise RuntimeError("boilerplate failed")

    class FakeLogger:
        def __init__(self) -> None:
            self.exception_calls = []

        def info(self, message, **context) -> None:
            pass

        def exception(self, message, **context) -> None:
            self.exception_calls.append((message, context))

    monkeypatch.setattr(handler_module, "service", FailingService())
    fake_logger = FakeLogger()
    monkeypatch.setattr(handler_module, "logger", fake_logger)

    try:
        handler_module.handler({}, FakeLambdaContext())
    except RuntimeError as error:
        assert str(error) == "boilerplate failed"
    else:
        raise AssertionError("Expected handler to propagate the service error")

    assert fake_logger.exception_calls == [("Failed to execute boilerplate Lambda", {})]


def test_lambda_handler_uses_toolkit_logger_with_lambda_context(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)

    log_stream = io.StringIO()
    original_stream = handler_module.logger.registered_handler.stream

    try:
        handler_module.logger.registered_handler.setStream(log_stream)

        handler_module.lambda_handler({}, FakeLambdaContext())

        logs = [
            json.loads(line)
            for line in log_stream.getvalue().splitlines()
            if line.strip()
        ]

        assert logs

        first_log = logs[0]

        assert first_log["message"] == "Starting boilerplate Lambda"
        assert first_log["service"] == "boilerplate-test"
        assert first_log["function_name"] == "boilerplate-test"
        assert first_log["function_request_id"] == "test-request-id"
        assert first_log["function_memory_size"] == 128
        assert first_log["function_arn"] == (
            "arn:aws:lambda:us-east-1:123456789012:function:boilerplate-test"
        )
    finally:
        handler_module.logger.registered_handler.setStream(original_stream)
