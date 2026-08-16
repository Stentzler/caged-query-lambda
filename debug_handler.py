import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

LOCAL_ENVIRONMENT_DEFAULTS = {
    # "AWS_ACCESS_KEY_ID": "local",
    # "AWS_SECRET_ACCESS_KEY": "local",
    "AWS_DEFAULT_REGION": "us-east-1",
    "ENVIRONMENT": "local",
    "SOURCE_NAME": "caged-query-local",
    "METRICS_TABLE_NAME": "caged_geo_job_metrics",
    "DATASET_CATALOG_TABLE_NAME": "caged_dataset_catalog",
    "CBO_LOOKUP_TABLE_NAME": "caged_cbo_lookup",
    "CBO_FAMILY_CODE_INDEX_NAME": "family_code-index",
    "GEO_LOOKUP_TABLE_NAME": "caged_geo_lookup",
    # "DYNAMODB_ENDPOINT_URL": "http://127.0.0.1:8000",
    "POWERTOOLS_SERVICE_NAME": "caged-query-local",
    "POWERTOOLS_LOG_LEVEL": "INFO",
    "POWERTOOLS_LOG_EVENT": "false",
}

for variable_name, default_value in LOCAL_ENVIRONMENT_DEFAULTS.items():
    os.environ.setdefault(variable_name, default_value)

sys.path.insert(0, str(SRC_DIR))

from handler import lambda_handler  # noqa: E402

LOCAL_EVENTS = {
    "country-all": PROJECT_ROOT / "events" / "event-country-all.json",
    "dataset-catalog": {
        "queryStringParameters": {
            "operation": "getDatasetCatalog",
        },
    },
}


class LocalLambdaContext:
    function_name = "local-caged-query-lambda"
    function_version = "$LATEST"
    invoked_function_arn = (
        "arn:aws:lambda:local:000000000000:function:local-caged-query-lambda"
    )
    memory_limit_in_mb = 128
    aws_request_id = "local-request-id"
    log_group_name = "/aws/lambda/local-caged-query-lambda"
    log_stream_name = "local"


def main() -> None:
    event_name = sys.argv[1] if len(sys.argv) > 1 else "country-all"
    event = _load_event(event_name)

    response = lambda_handler(event, LocalLambdaContext())

    print(json.dumps(response, indent=2, ensure_ascii=False))


def _load_event(event_name: str) -> dict:
    event_source = LOCAL_EVENTS.get(event_name)
    if event_source is None:
        available_events = ", ".join(sorted(LOCAL_EVENTS))
        raise ValueError(
            f"Unknown event '{event_name}'. Use one of: {available_events}"
        )

    if isinstance(event_source, Path):
        event_text = event_source.read_text() if event_source.exists() else ""
        return json.loads(event_text) if event_text.strip() else {}

    return event_source


if __name__ == "__main__":
    main()
