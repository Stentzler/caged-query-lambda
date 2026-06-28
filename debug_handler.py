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
    # "DYNAMODB_ENDPOINT_URL": "http://127.0.0.1:8000",
    "POWERTOOLS_SERVICE_NAME": "caged-query-local",
    "POWERTOOLS_LOG_LEVEL": "INFO",
    "POWERTOOLS_LOG_EVENT": "false",
}

for variable_name, default_value in LOCAL_ENVIRONMENT_DEFAULTS.items():
    os.environ.setdefault(variable_name, default_value)

sys.path.insert(0, str(SRC_DIR))

from handler import lambda_handler  # noqa: E402


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
    event_path = PROJECT_ROOT / "events" / "event-country-all.json"
    event_text = event_path.read_text() if event_path.exists() else ""
    event = json.loads(event_text) if event_text.strip() else {}

    response = lambda_handler(event, LocalLambdaContext())

    print(response)


if __name__ == "__main__":
    main()
