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
    cbo_lookup_table_name=settings.CBO_LOOKUP_TABLE_NAME,
    cbo_family_code_index_name=settings.CBO_FAMILY_CODE_INDEX_NAME,
    geo_lookup_table_name=settings.GEO_LOOKUP_TABLE_NAME,
    dataset_id=settings.DATASET_ID,
    batch_get_max_retries=settings.BATCH_GET_MAX_RETRIES,
)
service = MetricsService(repository=repository, settings=settings)


@inject_lambda_context(logger)
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    logger.info("Starting CAGED metrics query")

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

    _log_success(result)
    return _response(200, result)


def _log_success(result: dict[str, Any]) -> None:
    query = result.get("query")
    months = result.get("months")
    if isinstance(query, dict) and isinstance(months, dict):
        logger.info(
            "Finished CAGED metrics query",
            **_metrics_log_context(result, query, months),
        )
        return

    logger.info("Finished CAGED dataset catalog query")


def _metrics_log_context(
    result: dict[str, Any],
    query: dict[str, Any],
    months: dict[str, Any],
) -> dict[str, Any]:
    location = (
        result.get("location") if isinstance(result.get("location"), dict) else {}
    )
    profession = (
        result.get("profession") if isinstance(result.get("profession"), dict) else {}
    )
    profession_code = query.get("profession_code")
    location_type = query.get("location_type")

    context = {
        "month_count": len(months),
        "location_type": location_type,
        "location_code": None if location_type == "COUNTRY" else location.get("code"),
        "location_name": _location_name(location),
        "from": query.get("from"),
        "to": query.get("to"),
    }
    if profession_code and profession_code != "ALL":
        context["profession_code"] = profession_code
        context["profession_name"] = profession.get("title")

    return context


def _location_name(location: dict[str, Any]) -> Any:
    return location.get("name") or location.get("type")


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": settings.CORS_ALLOWED_ORIGIN,
        },
        "body": json.dumps(body, ensure_ascii=False, separators=(",", ":")),
    }
