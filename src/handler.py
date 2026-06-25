from typing import Any

from serverless_toolkit.observability.lambda_logger import (
    get_lambda_logger,
    inject_lambda_context,
)

from service import BoilerplateService
from settings import Settings

settings = Settings()
logger = get_lambda_logger()
service = BoilerplateService(settings=settings)


@inject_lambda_context(logger)
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    logger.info("Starting boilerplate Lambda")

    try:
        result = service.execute(event)
    except Exception:
        logger.exception("Failed to execute boilerplate Lambda")
        raise

    logger.info("Finished boilerplate Lambda", result=result)
    return result


lambda_handler = handler
