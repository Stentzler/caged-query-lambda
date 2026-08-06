import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from exceptions import DatasetCatalogUnavailableError, InvalidMetricsQueryError
from repository import MetricsRepository
from settings import Settings

MetricsPayload = dict[str, int | float]
MONTH_PATTERN = re.compile(r"^\d{6}$")
MONEY_QUANTIZER = Decimal("0.01")
GET_DATASET_CATALOG_OPERATION = "getDatasetCatalog"
ALL_PROFESSIONS_CODE = "ALL"
COUNTRY_CODE = "BR"
COUNTRY_NAME = "Brasil"
LOCATION_TYPES = {"COUNTRY", "STATE", "CITY"}
BRAZILIAN_STATE_NAMES = {
    "11": "Rondônia",
    "12": "Acre",
    "13": "Amazonas",
    "14": "Roraima",
    "15": "Pará",
    "16": "Amapá",
    "17": "Tocantins",
    "21": "Maranhão",
    "22": "Piauí",
    "23": "Ceará",
    "24": "Rio Grande do Norte",
    "25": "Paraíba",
    "26": "Pernambuco",
    "27": "Alagoas",
    "28": "Sergipe",
    "29": "Bahia",
    "31": "Minas Gerais",
    "32": "Espírito Santo",
    "33": "Rio de Janeiro",
    "35": "São Paulo",
    "41": "Paraná",
    "42": "Santa Catarina",
    "43": "Rio Grande do Sul",
    "50": "Mato Grosso do Sul",
    "51": "Mato Grosso",
    "52": "Goiás",
    "53": "Distrito Federal",
}
BRAZILIAN_STATE_CODES = tuple(BRAZILIAN_STATE_NAMES)


@dataclass(frozen=True)
class MetricsQuery:
    location_type: str
    location_code: str | None
    profession_code: str
    start_month: str
    end_month: str
    months: tuple[str, ...]


class MetricsService:
    def __init__(self, repository: MetricsRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def execute(self, event: object) -> dict[str, Any]:
        if self._is_dataset_catalog_request(event):
            return self._get_dataset_catalog()

        parameters = self._get_query_parameters(event)
        availability = self._load_availability()
        query = self._build_query(parameters, availability)
        available_months = set(availability["available_months"])
        readable_months = [month for month in query.months if month in available_months]
        if not readable_months:
            raise InvalidMetricsQueryError(
                "The requested range is outside available dataset months"
            )

        keys = self._build_metric_keys(query, readable_months)
        items = self._repository.batch_get_metrics(keys)
        monthly_metrics = self._build_monthly_metrics(query, items, available_months)

        return {
            "dataset": self._settings.DATASET_ID,
            "catalog_version": str(availability["catalog_version"]),
            "query": {
                "location_type": query.location_type,
                "location_code": query.location_code,
                "profession_code": query.profession_code,
                "from": query.start_month,
                "to": query.end_month,
            },
            "location": self._build_location(query, items),
            "profession": self._build_profession(query, items),
            "months": monthly_metrics,
        }

    def _is_dataset_catalog_request(self, event: object) -> bool:
        if not isinstance(event, dict):
            return False

        return (
            event.get("operation") == GET_DATASET_CATALOG_OPERATION
            or self._get_operation_parameter(event) == GET_DATASET_CATALOG_OPERATION
        )

    def _get_operation_parameter(self, event: dict[str, Any]) -> str | None:
        parameters = event.get("queryStringParameters") or {}
        if not isinstance(parameters, dict):
            return None

        operation = parameters.get("operation")
        return str(operation) if operation is not None else None

    def _get_dataset_catalog(self) -> dict[str, Any]:
        return self._to_json_safe(self._repository.get_dataset_catalog())

    def _to_json_safe(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return self._json_number(value)
        if isinstance(value, dict):
            return {str(key): self._to_json_safe(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [self._to_json_safe(item) for item in value]
        if isinstance(value, set):
            return sorted(self._to_json_safe(item) for item in value)

        return value

    def _get_query_parameters(self, event: object) -> dict[str, str]:
        if not isinstance(event, dict):
            raise InvalidMetricsQueryError("Lambda event must be a JSON object")

        parameters = event.get("queryStringParameters") or {}
        if not isinstance(parameters, dict):
            raise InvalidMetricsQueryError(
                "queryStringParameters must be a JSON object"
            )

        return {
            str(key): str(value)
            for key, value in parameters.items()
            if value is not None
        }

    def _load_availability(self) -> dict[str, Any]:
        availability = self._repository.get_availability()
        available_months = availability.get("available_months")
        latest_month = availability.get("latest_available_month")
        catalog_version = availability.get("catalog_version") or availability.get(
            "updated_at"
        )

        if (
            not isinstance(available_months, list)
            or not available_months
            or not latest_month
            or not catalog_version
        ):
            raise DatasetCatalogUnavailableError(
                "Dataset availability metadata is invalid"
            )

        normalized_months = sorted({str(month) for month in available_months})
        for month in normalized_months:
            if not self._is_valid_month(month):
                raise DatasetCatalogUnavailableError(
                    "available_months contains an invalid month"
                )

        latest_month = str(latest_month)
        if not self._is_valid_month(latest_month):
            raise DatasetCatalogUnavailableError("latest_available_month is invalid")
        if latest_month not in normalized_months:
            raise DatasetCatalogUnavailableError(
                "latest_available_month is not listed in available_months"
            )

        return {
            **availability,
            "available_months": normalized_months,
            "latest_available_month": latest_month,
            "catalog_version": str(catalog_version),
        }

    def _build_query(
        self,
        parameters: dict[str, str],
        availability: dict[str, Any],
    ) -> MetricsQuery:
        location_type = parameters.get("locationType", "").strip().upper()
        if location_type not in LOCATION_TYPES:
            raise InvalidMetricsQueryError(f"locationType must be {LOCATION_TYPES}")

        location_code = parameters.get("locationCode")
        if location_type == "COUNTRY":
            location_code = None
        elif not location_code or not location_code.strip():
            raise InvalidMetricsQueryError(
                "locationCode is required for STATE and CITY queries"
            )
        else:
            location_code = location_code.strip()

        profession_code = (
            parameters.get("professionCode", ALL_PROFESSIONS_CODE).strip().upper()
        )
        if not profession_code:
            raise InvalidMetricsQueryError("professionCode cannot be empty")

        start_month = parameters.get("from")
        end_month = parameters.get("to")
        if bool(start_month) != bool(end_month):
            raise InvalidMetricsQueryError("from and to must be provided together")

        if not start_month:
            start_month = availability["latest_available_month"]
            end_month = start_month

        self._validate_month(start_month, "from")
        self._validate_month(end_month, "to")
        if start_month > end_month:
            raise InvalidMetricsQueryError("from cannot be later than to")
        if end_month > availability["latest_available_month"]:
            raise InvalidMetricsQueryError(
                "to cannot be later than latest_available_month"
            )

        months = tuple(self._month_range(start_month, end_month))
        if len(months) > self._settings.MAX_QUERY_MONTHS:
            raise InvalidMetricsQueryError(
                f"The requested range cannot exceed "
                f"{self._settings.MAX_QUERY_MONTHS} months"
            )

        return MetricsQuery(
            location_type=location_type,
            location_code=location_code,
            profession_code=profession_code,
            start_month=start_month,
            end_month=end_month,
            months=months,
        )

    def _validate_month(self, month: str, field_name: str) -> None:
        if not MONTH_PATTERN.fullmatch(month):
            raise InvalidMetricsQueryError(f"{field_name} must use YYYYMM format")

        month_number = int(month[4:])
        if month_number < 1 or month_number > 12:
            raise InvalidMetricsQueryError(f"{field_name} must contain a valid month")

    def _is_valid_month(self, month: str) -> bool:
        return bool(MONTH_PATTERN.fullmatch(month) and 1 <= int(month[4:]) <= 12)

    def _month_range(self, start_month: str, end_month: str) -> list[str]:
        current_year = int(start_month[:4])
        current_month = int(start_month[4:])
        end_year = int(end_month[:4])
        end_month_number = int(end_month[4:])
        months: list[str] = []

        while (current_year, current_month) <= (end_year, end_month_number):
            months.append(f"{current_year:04d}{current_month:02d}")
            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1

        return months

    def _build_metric_keys(
        self,
        query: MetricsQuery,
        readable_months: list[str],
    ) -> list[dict[str, str]]:
        location_codes = (
            BRAZILIAN_STATE_CODES
            if query.location_type == "COUNTRY"
            else (query.location_code,)
        )
        key_location_type = (
            "STATE" if query.location_type == "COUNTRY" else query.location_type
        )

        return [
            {
                "PK": f"LOC#{key_location_type}#{location_code}#MONTH#{month}",
                "SK": f"PROF#{query.profession_code}",
            }
            for month in readable_months
            for location_code in location_codes
        ]

    def _build_monthly_metrics(
        self,
        query: MetricsQuery,
        items: list[dict[str, Any]],
        available_months: set[str],
    ) -> dict[str, MetricsPayload]:
        items_by_month: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            month = str(item.get("reference_month", ""))
            items_by_month.setdefault(month, []).append(item)

        monthly_metrics: dict[str, MetricsPayload] = {}
        for month in query.months:
            month_items = items_by_month.get(month, [])
            if month not in available_months:
                monthly_metrics[month] = self._empty_metrics()
            elif query.location_type == "COUNTRY":
                monthly_metrics[month] = self._aggregate_country(month_items)
            elif len(month_items) == 1:
                monthly_metrics[month] = self._serialize_metrics(month_items[0])
            else:
                monthly_metrics[month] = self._empty_metrics()

        return monthly_metrics

    def _aggregate_country(self, items: list[dict[str, Any]]) -> MetricsPayload:
        totals = {
            field: sum(Decimal(str(item.get(field, 0))) for item in items)
            for field in (
                "admissions",
                "dismissals",
                "net_balance",
                "total_turnover",
                "salary_sum",
                "salary_count",
            )
        }

        salary_count = totals["salary_count"]
        avg_salary = (
            Decimal("0")
            if salary_count == 0
            else (totals["salary_sum"] / salary_count).quantize(
                MONEY_QUANTIZER,
                rounding=ROUND_HALF_UP,
            )
        )

        return {
            "admissions": self._json_number(totals["admissions"]),
            "dismissals": self._json_number(totals["dismissals"]),
            "net_balance": self._json_number(totals["net_balance"]),
            "total_turnover": self._json_number(totals["total_turnover"]),
            "avg_salary": self._json_money_number(avg_salary),
            "salary_sum": self._json_money_number(totals["salary_sum"]),
            "salary_count": self._json_number(salary_count),
        }

    def _serialize_metrics(self, item: dict[str, Any]) -> MetricsPayload:
        return {
            "admissions": self._json_number(Decimal(str(item.get("admissions", 0)))),
            "dismissals": self._json_number(Decimal(str(item.get("dismissals", 0)))),
            "net_balance": self._json_number(Decimal(str(item.get("net_balance", 0)))),
            "total_turnover": self._json_number(
                Decimal(str(item.get("total_turnover", 0)))
            ),
            "avg_salary": self._json_money_number(
                Decimal(str(item.get("avg_salary", 0)))
            ),
            "salary_sum": self._json_money_number(
                Decimal(str(item.get("salary_sum", 0)))
            ),
            "salary_count": self._json_number(
                Decimal(str(item.get("salary_count", 0)))
            ),
        }

    def _empty_metrics(self) -> MetricsPayload:
        return {
            "admissions": 0,
            "dismissals": 0,
            "net_balance": 0,
            "total_turnover": 0,
            "avg_salary": 0.0,
            "salary_sum": 0.0,
            "salary_count": 0,
        }

    def _build_location(
        self,
        query: MetricsQuery,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if query.location_type == "COUNTRY":
            return {
                "type": "COUNTRY",
                "code": COUNTRY_CODE,
                "name": COUNTRY_NAME,
            }

        first_item = next(iter(items), {})
        location = {
            "type": query.location_type,
            "code": query.location_code,
            "name": (
                str(first_item["location_name"])
                if first_item.get("location_name")
                else None
            ),
        }
        if query.location_type == "CITY":
            location["state"] = self._build_city_state(query, first_item)

        return location

    def _build_city_state(
        self,
        query: MetricsQuery,
        first_item: dict[str, Any],
    ) -> dict[str, str | None]:
        state_code = str(
            first_item.get("state_code") or (query.location_code or "")[:2]
        )
        return {
            "code": state_code or None,
            "name": BRAZILIAN_STATE_NAMES.get(state_code),
        }

    def _build_profession(
        self,
        query: MetricsQuery,
        items: list[dict[str, Any]],
    ) -> dict[str, str | None]:
        first_item = next(iter(items), {})
        return {
            "code": query.profession_code,
            "title": (
                str(first_item["family_title"])
                if first_item.get("family_title")
                else None
            ),
        }

    def _json_number(self, value: Decimal) -> int | float:
        if value == value.to_integral_value():
            return int(value)
        return float(value)

    def _json_money_number(self, value: Decimal) -> float:
        return float(value)
