import json
from typing import Any

from serverless_toolkit.aws.dynamodb import get_dynamodb_resource
from serverless_toolkit.observability.lambda_logger import (
    get_lambda_logger,
    inject_lambda_context,
)

from exceptions import (
    DatasetCatalogUnavailableError,
    InvalidMetricsQueryError,
    MetricsDataUnavailableError,
)
from repository import MetricsRepository
from service import MetricsService
from settings import Settings

settings = Settings()
logger = get_lambda_logger()
repository = MetricsRepository(
    dynamodb_resource=get_dynamodb_resource(),
    metrics_table_name=settings.METRICS_TABLE_NAME,
    catalog_table_name=settings.DATASET_CATALOG_TABLE_NAME,
    dataset_id=settings.DATASET_ID,
    batch_get_max_retries=settings.BATCH_GET_MAX_RETRIES,
)
service = MetricsService(repository=repository, settings=settings)


@inject_lambda_context(logger)
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    logger.debug("Starting CAGED metrics query")

    try:
        result = service.execute(event)
    except InvalidMetricsQueryError as error:
        logger.warning("Rejected invalid metrics query", error=str(error))
        return _response(400, {"message": str(error)})
    except (DatasetCatalogUnavailableError, MetricsDataUnavailableError) as error:
        logger.exception("CAGED metrics data is temporarily unavailable")
        return _response(503, {"message": str(error)})
    except Exception:
        logger.exception("Failed to execute CAGED metrics query")
        return _response(500, {"message": "Internal server error"})

    logger.info(
        "Finished CAGED metrics query",
        month_count=len(result["months"]),
        location_type=result["query"]["location_type"],
    )
    return _response(200, result)


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": settings.CORS_ALLOWED_ORIGIN,
        },
        "body": json.dumps(body, ensure_ascii=False, separators=(",", ":")),
    }
