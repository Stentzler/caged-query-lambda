import pytest

from exceptions import (
    DatasetCatalogUnavailableError,
    MetricsDataUnavailableError,
)
from repository import MetricsRepository


class FakeTable:
    def __init__(self, items) -> None:
        self.items = items
        self.calls = []
        self.query_calls = []

    def get_item(self, **kwargs):
        self.calls.append(kwargs)
        key = tuple(kwargs["Key"].values())
        return {"Item": self.items[key]} if key in self.items else {}

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        family_code = kwargs["ExpressionAttributeValues"][":family_code"]
        return {
            "Items": [
                item
                for item in self.items.values()
                if item.get("family_code") == family_code
            ][: kwargs["Limit"]]
        }


class FakeResource:
    def __init__(self, catalog_items=None, batch_responses=None) -> None:
        self.catalog_table = FakeTable(catalog_items or {})
        self.cbo_lookup_table = FakeTable(
            {
                ("2251",): {
                    "family_code": "2251",
                    "family_title": "Médicos clínicos",
                }
            }
        )
        self.geo_lookup_table = FakeTable(
            {
                ("412820", "CITY"): {
                    "code": "412820",
                    "type": "CITY",
                    "name": "União da Vitória",
                    "state_code": "41",
                    "state_name": "Paraná",
                }
            }
        )
        self.batch_responses = list(batch_responses or [])
        self.batch_calls = []

    def Table(self, name):
        return {
            "catalog": self.catalog_table,
            "cbo_lookup": self.cbo_lookup_table,
            "geo_lookup": self.geo_lookup_table,
        }[name]

    def batch_get_item(self, **kwargs):
        self.batch_calls.append(kwargs)
        return self.batch_responses.pop(0)


def build_repository(resource: FakeResource, retries: int = 3) -> MetricsRepository:
    return MetricsRepository(
        dynamodb_resource=resource,
        metrics_table_name="metrics",
        catalog_table_name="catalog",
        cbo_lookup_table_name="cbo_lookup",
        cbo_family_code_index_name="family_code-index",
        geo_lookup_table_name="geo_lookup",
        dataset_id="CAGED_GEO_JOB_METRICS",
        batch_get_max_retries=retries,
    )


def test_get_availability_reads_dataset_metadata_item() -> None:
    resource = FakeResource(
        catalog_items={
            ("DATASET#CAGED_GEO_JOB_METRICS", "METADATA"): {
                "available_months": ["202604"],
                "latest_available_month": "202604",
            },
        }
    )

    availability = build_repository(resource).get_availability()

    assert availability["latest_available_month"] == "202604"
    assert all(call["ConsistentRead"] is True for call in resource.catalog_table.calls)


def test_get_dataset_catalog_reads_dataset_metadata_item() -> None:
    resource = FakeResource(
        catalog_items={
            ("DATASET#CAGED_GEO_JOB_METRICS", "METADATA"): {
                "PK": "DATASET#CAGED_GEO_JOB_METRICS",
                "SK": "METADATA",
                "latest_available_month": "202604",
            },
        }
    )

    catalog = build_repository(resource).get_dataset_catalog()

    assert catalog["PK"] == "DATASET#CAGED_GEO_JOB_METRICS"
    assert resource.catalog_table.calls == [
        {
            "Key": {
                "PK": "DATASET#CAGED_GEO_JOB_METRICS",
                "SK": "METADATA",
            },
            "ConsistentRead": True,
        }
    ]


def test_get_availability_rejects_missing_metadata() -> None:
    with pytest.raises(DatasetCatalogUnavailableError, match="metadata"):
        build_repository(FakeResource()).get_availability()


def test_get_dataset_catalog_rejects_missing_metadata() -> None:
    with pytest.raises(DatasetCatalogUnavailableError, match="catalog metadata"):
        build_repository(FakeResource()).get_dataset_catalog()


def test_get_location_lookup_reads_geo_lookup_item() -> None:
    resource = FakeResource()

    lookup = build_repository(resource).get_location_lookup(
        location_type="CITY",
        location_code="412820",
    )

    assert lookup == {
        "code": "412820",
        "type": "CITY",
        "name": "União da Vitória",
        "state_code": "41",
        "state_name": "Paraná",
    }
    assert resource.geo_lookup_table.calls == [
        {
            "Key": {
                "code": "412820",
                "type": "CITY",
            },
            "ConsistentRead": True,
        }
    ]


def test_get_profession_lookup_queries_family_code_index() -> None:
    resource = FakeResource()

    lookup = build_repository(resource).get_profession_lookup("2251")

    assert lookup == {
        "family_code": "2251",
        "family_title": "Médicos clínicos",
    }
    assert resource.cbo_lookup_table.query_calls == [
        {
            "IndexName": "family_code-index",
            "KeyConditionExpression": "family_code = :family_code",
            "ExpressionAttributeValues": {":family_code": "2251"},
            "ProjectionExpression": "family_code, family_title",
            "Limit": 1,
        }
    ]


def test_batch_get_chunks_requests_at_100_keys() -> None:
    resource = FakeResource(
        batch_responses=[
            {"Responses": {"metrics": [{"PK": "first"}]}},
            {"Responses": {"metrics": [{"PK": "last"}]}},
        ]
    )
    keys = [{"PK": f"PK#{index}", "SK": "SK"} for index in range(101)]

    items = build_repository(resource).batch_get_metrics(keys)

    assert items == [{"PK": "first"}, {"PK": "last"}]
    assert [
        len(call["RequestItems"]["metrics"]["Keys"]) for call in resource.batch_calls
    ] == [100, 1]


def test_batch_get_retries_unprocessed_keys() -> None:
    pending_key = {"PK": "PK#1", "SK": "SK"}
    resource = FakeResource(
        batch_responses=[
            {
                "Responses": {"metrics": []},
                "UnprocessedKeys": {"metrics": {"Keys": [pending_key]}},
            },
            {"Responses": {"metrics": [{"PK": "PK#1", "SK": "SK"}]}},
        ]
    )

    items = build_repository(resource).batch_get_metrics([pending_key])

    assert items == [{"PK": "PK#1", "SK": "SK"}]
    assert len(resource.batch_calls) == 2


def test_batch_get_fails_after_retry_limit() -> None:
    pending_key = {"PK": "PK#1", "SK": "SK"}
    response = {
        "Responses": {"metrics": []},
        "UnprocessedKeys": {"metrics": {"Keys": [pending_key]}},
    }
    resource = FakeResource(batch_responses=[response, response])

    with pytest.raises(MetricsDataUnavailableError, match="1 metric keys"):
        build_repository(resource, retries=1).batch_get_metrics([pending_key])
