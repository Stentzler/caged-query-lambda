from decimal import Decimal

import pytest

from exceptions import DatasetCatalogUnavailableError, InvalidMetricsQueryError
from service import BRAZILIAN_STATE_CODES, MetricsService
from settings import Settings


class FakeRepository:
    def __init__(self, items=None, availability=None) -> None:
        self.items = items or []
        self.availability = availability or {
            "available_months": ["202501", "202502", "202604"],
            "latest_available_month": "202604",
            "updated_at": "2026-06-25T21:00:00Z",
        }
        self.requested_keys = []

    def get_availability(self):
        return self.availability

    def batch_get_metrics(self, keys):
        self.requested_keys = list(keys)
        return self.items


def build_service(repository: FakeRepository) -> MetricsService:
    return MetricsService(
        repository=repository,
        settings=Settings(MAX_QUERY_MONTHS=24),
    )


def event(**parameters) -> dict:
    return {"queryStringParameters": parameters}


def empty_metrics() -> dict:
    return {
        "admissions": 0,
        "dismissals": 0,
        "net_balance": 0,
        "total_turnover": 0,
        "avg_salary": 0.0,
        "salary_sum": 0.0,
        "salary_count": 0,
    }


def metric_item(
    *,
    month: str = "202604",
    location_type: str = "STATE",
    location_code: str = "29",
    location_name: str = "Bahia",
    state_code: str = "29",
    profession_code: str = "ALL",
    admissions: int = 10,
    dismissals: int = 4,
    salary_sum: str = "3000",
    salary_count: int = 2,
    avg_salary: str | None = None,
) -> dict:
    average_salary = (
        Decimal(avg_salary)
        if avg_salary is not None
        else Decimal(salary_sum) / salary_count
        if salary_count
        else Decimal("0")
    )
    return {
        "PK": f"LOC#{location_type}#{location_code}#MONTH#{month}",
        "SK": f"PROF#{profession_code}",
        "reference_month": month,
        "location_type": location_type,
        "location_code": location_code,
        "location_name": location_name,
        "state_code": state_code,
        "family_code": profession_code,
        "family_title": (
            "All professions" if profession_code == "ALL" else "Software developers"
        ),
        "admissions": admissions,
        "dismissals": dismissals,
        "net_balance": admissions - dismissals,
        "total_turnover": admissions + dismissals,
        "salary_sum": Decimal(salary_sum),
        "salary_count": salary_count,
        "avg_salary": average_salary,
    }


def test_state_query_uses_latest_month_and_all_professions_by_default() -> None:
    repository = FakeRepository(items=[metric_item()])
    service = build_service(repository)

    response = service.execute(event(locationType="state", locationCode="29"))

    assert repository.requested_keys == [
        {
            "PK": "LOC#STATE#29#MONTH#202604",
            "SK": "PROF#ALL",
        }
    ]
    assert response["query"] == {
        "location_type": "STATE",
        "location_code": "29",
        "profession_code": "ALL",
        "from": "202604",
        "to": "202604",
    }
    assert response["catalog_version"] == "2026-06-25T21:00:00Z"
    assert response["months"]["202604"] == {
        "admissions": 10,
        "dismissals": 4,
        "net_balance": 6,
        "total_turnover": 14,
        "avg_salary": 1500,
        "salary_sum": 3000,
        "salary_count": 2,
    }


def test_city_profession_query_returns_range_with_missing_months() -> None:
    repository = FakeRepository(
        items=[
            metric_item(
                month="202501",
                location_type="CITY",
                location_code="292070",
                profession_code="2124",
            ),
            metric_item(
                month="202502",
                location_type="CITY",
                location_code="292070",
                profession_code="2124",
            ),
        ],
        availability={
            "available_months": ["202501", "202502", "202504"],
            "latest_available_month": "202504",
            "updated_at": "2026-06-25T21:00:00Z",
        },
    )
    service = build_service(repository)

    response = service.execute(
        event(
            locationType="CITY",
            locationCode="292070",
            professionCode="2124",
            **{"from": "202501", "to": "202504"},
        )
    )

    assert [key["PK"] for key in repository.requested_keys] == [
        "LOC#CITY#292070#MONTH#202501",
        "LOC#CITY#292070#MONTH#202502",
        "LOC#CITY#292070#MONTH#202504",
    ]
    assert response["months"]["202501"] is not None
    assert response["months"]["202502"] is not None
    assert response["months"]["202503"] == empty_metrics()
    assert response["months"]["202504"] == empty_metrics()


def test_city_location_includes_parent_state() -> None:
    repository = FakeRepository(
        items=[
            metric_item(
                location_type="CITY",
                location_code="292070",
                location_name="Maraú",
                state_code="29",
            )
        ]
    )

    response = build_service(repository).execute(
        event(locationType="CITY", locationCode="292070")
    )

    assert response["location"] == {
        "type": "CITY",
        "code": "292070",
        "name": "Maraú",
        "state": {
            "code": "29",
            "name": "Bahia",
        },
    }


def test_country_query_aggregates_all_states_with_weighted_salary() -> None:
    items = [
        metric_item(
            state_code=state_code,
            location_code=state_code,
            admissions=1,
            dismissals=0,
            salary_sum="1000" if state_code == "11" else "2000",
            salary_count=1 if state_code == "11" else 2,
        )
        for state_code in BRAZILIAN_STATE_CODES
    ]
    repository = FakeRepository(items=items)
    service = build_service(repository)

    response = service.execute(event(locationType="COUNTRY"))

    assert len(repository.requested_keys) == 27
    metrics = response["months"]["202604"]
    assert metrics is not None
    assert metrics["admissions"] == 27
    assert metrics["salary_sum"] == 53000
    assert metrics["salary_count"] == 53
    assert metrics["avg_salary"] == 1000
    assert isinstance(metrics["avg_salary"], float)
    assert response["location"] == {
        "type": "COUNTRY",
        "code": "BR",
        "name": "Brasil",
    }


def test_country_all_professions_salary_uses_state_salary_sum() -> None:
    items = [
        metric_item(
            state_code=state_code,
            location_code=state_code,
            salary_sum="30000",
            salary_count=10,
            avg_salary="9999",
        )
        for state_code in BRAZILIAN_STATE_CODES
    ]
    repository = FakeRepository(items=items)

    response = build_service(repository).execute(event(locationType="COUNTRY"))

    metrics = response["months"]["202604"]
    assert metrics is not None
    assert metrics["avg_salary"] == 3000
    assert metrics["salary_sum"] == 810000
    assert metrics["salary_count"] == 270


def test_country_specific_profession_uses_state_salary_sum() -> None:
    items = [
        metric_item(
            state_code=state_code,
            location_code=state_code,
            profession_code="2124",
            salary_sum="30000",
            salary_count=10,
            avg_salary="9999",
        )
        for state_code in BRAZILIAN_STATE_CODES
    ]
    repository = FakeRepository(items=items)

    response = build_service(repository).execute(
        event(locationType="COUNTRY", professionCode="2124")
    )

    metrics = response["months"]["202604"]
    assert metrics is not None
    assert metrics["avg_salary"] == 3000
    assert metrics["salary_sum"] == 810000
    assert metrics["salary_count"] == 270


def test_country_missing_state_record_counts_as_zero() -> None:
    repository = FakeRepository(
        items=[
            metric_item(
                state_code=code,
                location_code=code,
                admissions=1,
                dismissals=0,
                salary_sum="1000",
                salary_count=1,
            )
            for code in BRAZILIAN_STATE_CODES[:-1]
        ]
    )

    response = build_service(repository).execute(event(locationType="COUNTRY"))

    metrics = response["months"]["202604"]
    assert metrics is not None
    assert metrics["admissions"] == 26
    assert metrics["avg_salary"] == 1000
    assert metrics["salary_sum"] == 26000
    assert metrics["salary_count"] == 26


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({}, "locationType"),
        ({"locationType": "REGION"}, "locationType"),
        ({"locationType": "STATE"}, "locationCode"),
        (
            {"locationType": "CITY", "locationCode": "1", "from": "202501"},
            "provided together",
        ),
        (
            {
                "locationType": "CITY",
                "locationCode": "1",
                "from": "202513",
                "to": "202513",
            },
            "valid month",
        ),
        (
            {
                "locationType": "CITY",
                "locationCode": "1",
                "from": "202502",
                "to": "202501",
            },
            "later than",
        ),
        (
            {
                "locationType": "CITY",
                "locationCode": "1",
                "from": "202501",
                "to": "202605",
            },
            "latest_available_month",
        ),
        (
            {
                "locationType": "STATE",
                "locationCode": "29",
                "from": "202201",
                "to": "202210",
            },
            "outside available dataset months",
        ),
    ],
)
def test_invalid_queries_are_rejected(parameters, message) -> None:
    with pytest.raises(InvalidMetricsQueryError, match=message):
        build_service(FakeRepository()).execute(event(**parameters))


def test_range_cannot_exceed_configured_limit() -> None:
    service = MetricsService(
        repository=FakeRepository(),
        settings=Settings(MAX_QUERY_MONTHS=2),
    )

    with pytest.raises(InvalidMetricsQueryError, match="cannot exceed 2 months"):
        service.execute(
            event(
                locationType="STATE",
                locationCode="29",
                **{"from": "202501", "to": "202503"},
            )
        )


def test_invalid_catalog_metadata_is_rejected() -> None:
    repository = FakeRepository(
        availability={
            "available_months": ["202501"],
            "latest_available_month": "202502",
            "updated_at": "2026-06-25T21:00:00Z",
        }
    )

    with pytest.raises(DatasetCatalogUnavailableError, match="not listed"):
        build_service(repository).execute(event(locationType="COUNTRY"))


def test_malformed_catalog_month_is_backend_failure() -> None:
    repository = FakeRepository(
        availability={
            "available_months": ["202513"],
            "latest_available_month": "202513",
            "updated_at": "2026-06-25T21:00:00Z",
        }
    )

    with pytest.raises(DatasetCatalogUnavailableError, match="invalid month"):
        build_service(repository).execute(event(locationType="COUNTRY"))
