import importlib
import json
import sys
from types import ModuleType


class FakeLambdaContext:
    function_name = "caged-query-test"
    function_version = "$LATEST"
    invoked_function_arn = (
        "arn:aws:lambda:us-east-1:123456789012:function:caged-query-test"
    )
    memory_limit_in_mb = 128
    aws_request_id = "test-request-id"
    log_group_name = "/aws/lambda/caged-query-test"
    log_stream_name = "2026/01/01/[$LATEST]abcdef"


def load_handler_module(monkeypatch) -> ModuleType:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("SOURCE_NAME", "caged-query-test")
    monkeypatch.setenv("POWERTOOLS_SERVICE_NAME", "caged-query-test")
    monkeypatch.setenv("POWERTOOLS_LOG_LEVEL", "INFO")
    monkeypatch.setenv("POWERTOOLS_LOG_EVENT", "false")
    monkeypatch.setenv("CORS_ALLOWED_ORIGIN", "https://example.com")
    sys.modules.pop("handler", None)

    return importlib.import_module("handler")


def test_handler_returns_api_gateway_response(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)
    expected = {
        "dataset": "CAGED_GEO_JOB_METRICS",
        "query": {"location_type": "STATE"},
        "months": {"202604": {"admissions": 1}},
    }

    class FakeService:
        def execute(self, event):
            assert event == {"queryStringParameters": {"locationType": "STATE"}}
            return expected

    monkeypatch.setattr(handler_module, "service", FakeService())

    response = handler_module.lambda_handler(
        {"queryStringParameters": {"locationType": "STATE"}},
        FakeLambdaContext(),
    )

    assert response["statusCode"] == 200
    assert response["headers"]["Access-Control-Allow-Origin"] == "https://example.com"
    assert json.loads(response["body"]) == expected


def test_handler_returns_dataset_catalog_response(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)
    expected = {
        "PK": "DATASET#CAGED_GEO_JOB_METRICS",
        "SK": "METADATA",
        "latest_available_month": "202604",
    }

    class FakeService:
        def execute(self, event):
            assert event == {
                "queryStringParameters": {"operation": "getDatasetCatalog"}
            }
            return expected

    monkeypatch.setattr(handler_module, "service", FakeService())

    response = handler_module.lambda_handler(
        {"queryStringParameters": {"operation": "getDatasetCatalog"}},
        FakeLambdaContext(),
    )

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == expected


def test_metrics_success_log_includes_query_context(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)
    info_calls = []

    class FakeLogger:
        def info(self, message, **kwargs):
            info_calls.append((message, kwargs))

        def warning(self, message, **kwargs):
            raise AssertionError(f"unexpected warning: {message} {kwargs}")

        def exception(self, message, **kwargs):
            raise AssertionError(f"unexpected exception: {message} {kwargs}")

    class FakeService:
        def execute(self, event):
            return {
                "query": {
                    "location_type": "CITY",
                    "location_code": "412820",
                    "profession_code": "2251",
                    "from": "202501",
                    "to": "202501",
                },
                "location": {
                    "type": "CITY",
                    "code": "412820",
                    "name": "União da Vitória",
                },
                "profession": {
                    "code": "2251",
                    "title": "Médicos clínicos",
                },
                "months": {"202501": {"admissions": 0}},
            }

    monkeypatch.setattr(handler_module, "logger", FakeLogger())
    monkeypatch.setattr(handler_module, "service", FakeService())

    handler_module.lambda_handler({}, FakeLambdaContext())

    assert info_calls[-1] == (
        "Finished CAGED metrics query",
        {
            "month_count": 1,
            "location_type": "CITY",
            "location_code": "412820",
            "location_name": "União da Vitória",
            "from": "202501",
            "to": "202501",
            "profession_code": "2251",
            "profession_name": "Médicos clínicos",
        },
    )


def test_metrics_success_log_omits_profession_context_for_all(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)
    info_calls = []

    class FakeLogger:
        def info(self, message, **kwargs):
            info_calls.append((message, kwargs))

        def warning(self, message, **kwargs):
            raise AssertionError(f"unexpected warning: {message} {kwargs}")

        def exception(self, message, **kwargs):
            raise AssertionError(f"unexpected exception: {message} {kwargs}")

    class FakeService:
        def execute(self, event):
            return {
                "query": {
                    "location_type": "COUNTRY",
                    "location_code": None,
                    "profession_code": "ALL",
                    "from": "202501",
                    "to": "202501",
                },
                "location": {
                    "type": "COUNTRY",
                    "code": "BR",
                    "name": "Brasil",
                },
                "profession": {
                    "code": "ALL",
                    "title": "All professions",
                },
                "months": {"202501": {"admissions": 0}},
            }

    monkeypatch.setattr(handler_module, "logger", FakeLogger())
    monkeypatch.setattr(handler_module, "service", FakeService())

    handler_module.lambda_handler({}, FakeLambdaContext())

    assert info_calls[-1] == (
        "Finished CAGED metrics query",
        {
            "month_count": 1,
            "location_type": "COUNTRY",
            "location_code": None,
            "location_name": "Brasil",
            "from": "202501",
            "to": "202501",
        },
    )


def test_handler_maps_invalid_query_to_400(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)

    class FakeService:
        def execute(self, event):
            raise handler_module.InvalidMetricsQueryError("invalid query")

    monkeypatch.setattr(handler_module, "service", FakeService())

    response = handler_module.lambda_handler({}, FakeLambdaContext())

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {"message": "invalid query"}


def test_handler_maps_data_unavailability_to_503(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)

    class FakeService:
        def execute(self, event):
            raise handler_module.DatasetCatalogUnavailableError("catalog unavailable")

    monkeypatch.setattr(handler_module, "service", FakeService())

    response = handler_module.lambda_handler({}, FakeLambdaContext())

    assert response["statusCode"] == 503


def test_handler_hides_unexpected_errors(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)

    class FakeService:
        def execute(self, event):
            raise RuntimeError("secret failure")

    monkeypatch.setattr(handler_module, "service", FakeService())

    response = handler_module.lambda_handler({}, FakeLambdaContext())

    assert response["statusCode"] == 500
    assert json.loads(response["body"]) == {"message": "Internal server error"}
