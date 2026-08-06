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
