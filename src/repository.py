from collections.abc import Iterable
from typing import Any, Protocol

from exceptions import (
    DatasetCatalogUnavailableError,
    MetricsDataUnavailableError,
)

BATCH_GET_LIMIT = 100


class DynamoDBTableProtocol(Protocol):
    def get_item(self, **kwargs: Any) -> dict[str, Any]: ...

    def query(self, **kwargs: Any) -> dict[str, Any]: ...


class DynamoDBResourceProtocol(Protocol):
    def Table(self, name: str) -> DynamoDBTableProtocol: ...

    def batch_get_item(self, **kwargs: Any) -> dict[str, Any]: ...


class MetricsRepository:
    """Read dataset availability and exact metric records from DynamoDB."""

    def __init__(
        self,
        dynamodb_resource: DynamoDBResourceProtocol,
        metrics_table_name: str,
        catalog_table_name: str,
        cbo_lookup_table_name: str,
        cbo_family_code_index_name: str,
        geo_lookup_table_name: str,
        dataset_id: str,
        batch_get_max_retries: int,
    ) -> None:
        self._dynamodb_resource = dynamodb_resource
        self._metrics_table_name = metrics_table_name
        self._catalog_table = dynamodb_resource.Table(catalog_table_name)
        self._cbo_lookup_table = dynamodb_resource.Table(cbo_lookup_table_name)
        self._cbo_family_code_index_name = cbo_family_code_index_name
        self._geo_lookup_table = dynamodb_resource.Table(geo_lookup_table_name)
        self._dataset_id = dataset_id
        self._batch_get_max_retries = batch_get_max_retries

    def get_availability(self) -> dict[str, Any]:
        availability = self._catalog_table.get_item(
            Key={
                "PK": f"DATASET#{self._dataset_id}",
                "SK": "METADATA",
            },
            ConsistentRead=True,
        ).get("Item")
        if not availability:
            raise DatasetCatalogUnavailableError(
                "Dataset availability metadata is unavailable"
            )

        return availability

    def get_dataset_catalog(self) -> dict[str, Any]:
        catalog = self._catalog_table.get_item(
            Key={
                "PK": f"DATASET#{self._dataset_id}",
                "SK": "METADATA",
            },
            ConsistentRead=True,
        ).get("Item")
        if not catalog:
            raise DatasetCatalogUnavailableError(
                "Dataset catalog metadata is unavailable"
            )

        return catalog

    def get_location_lookup(
        self,
        *,
        location_type: str,
        location_code: str,
    ) -> dict[str, Any] | None:
        return self._geo_lookup_table.get_item(
            Key={
                "code": location_code,
                "type": location_type,
            },
            ConsistentRead=True,
        ).get("Item")

    def get_profession_lookup(self, family_code: str) -> dict[str, Any] | None:
        response = self._cbo_lookup_table.query(
            IndexName=self._cbo_family_code_index_name,
            KeyConditionExpression="family_code = :family_code",
            ExpressionAttributeValues={":family_code": family_code},
            ProjectionExpression="family_code, family_title",
            Limit=1,
        )
        items = response.get("Items", [])
        return items[0] if items else None

    def batch_get_metrics(self, keys: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
        key_list = list(keys)
        items: list[dict[str, Any]] = []

        for start in range(0, len(key_list), BATCH_GET_LIMIT):
            chunk = key_list[start : start + BATCH_GET_LIMIT]
            items.extend(self._get_metric_chunk(chunk))

        return items

    def _get_metric_chunk(self, keys: list[dict[str, str]]) -> list[dict[str, Any]]:
        pending_keys = keys
        items: list[dict[str, Any]] = []

        for attempt in range(self._batch_get_max_retries + 1):
            response = self._dynamodb_resource.batch_get_item(
                RequestItems={
                    self._metrics_table_name: {
                        "Keys": pending_keys,
                        "ConsistentRead": False,
                    }
                }
            )
            items.extend(
                response.get("Responses", {}).get(self._metrics_table_name, [])
            )
            pending_keys = (
                response.get("UnprocessedKeys", {})
                .get(self._metrics_table_name, {})
                .get("Keys", [])
            )

            if not pending_keys:
                return items
            if attempt == self._batch_get_max_retries:
                break

        raise MetricsDataUnavailableError(
            f"DynamoDB did not process {len(pending_keys)} metric keys"
        )
