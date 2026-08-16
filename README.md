# CAGED Query Lambda

Read-only AWS Lambda used by the CAGED web application to retrieve monthly
geographic job metrics from DynamoDB.

The Lambda is packaged as a Python ZIP artifact and exposed through the
private API Gateway REST API route `GET /v1/metrics`.

## API

### `GET /v1/metrics`

Use query string parameters to choose the geography, optional profession, and
optional month range.

| Parameter | Required | Description |
| --- | --- | --- |
| `locationType` | Yes | `COUNTRY`, `STATE`, or `CITY` |
| `locationCode` | For `STATE` and `CITY` | IBGE state or city code. Ignored for `COUNTRY`. |
| `professionCode` | No | CBO family code. Defaults to `ALL`. |
| `from` | No | First month in `YYYYMM` format. Must be used with `to`. |
| `to` | No | Last month in `YYYYMM` format. Must be used with `from`. |

If `from` and `to` are omitted, the API returns only the catalog's
`latest_available_month`. Ranges are inclusive, limited to 24 months by default,
and must include at least one available dataset month.

Valid combinations:

| Request | Meaning |
| --- | --- |
| `?locationType=COUNTRY` | Brazil total, all professions, latest month |
| `?locationType=COUNTRY&professionCode=2124` | Brazil total for one CBO family |
| `?locationType=STATE&locationCode=35` | State total for Sao Paulo |
| `?locationType=CITY&locationCode=355030` | City total for Sao Paulo city |
| `?locationType=CITY&locationCode=355030&professionCode=2237&from=202501&to=202512` | City + CBO family for a month range |

Invalid combinations return `400` with a `message`, for example:

| Request problem | Error |
| --- | --- |
| Missing or unsupported `locationType` | `locationType` must be one of `COUNTRY`, `STATE`, or `CITY` |
| `STATE` or `CITY` without `locationCode` | `locationCode is required for STATE and CITY queries` |
| Only `from` or only `to` | `from and to must be provided together` |
| Month not `YYYYMM`, invalid month, `from > to`, or `to` after latest available month | Validation error message |
| Range longer than `MAX_QUERY_MONTHS` | `The requested range cannot exceed N months` |
| Range outside all available dataset months | `The requested range is outside available dataset months` |

Example request:

```http
GET /v1/metrics?locationType=CITY&locationCode=292070&professionCode=7842&from=202501&to=202502
```

Successful API Gateway responses use camelCase field names:

```json
{
  "dataset": "CAGED_GEO_JOB_METRICS",
  "catalogVersion": "2026-06-25T21:00:00Z",
  "query": {
    "locationType": "CITY",
    "locationCode": "292070",
    "professionCode": "7842",
    "from": "202501",
    "to": "202502"
  },
  "location": {
    "type": "CITY",
    "code": "292070",
    "name": "Maraú",
    "state": {
      "code": "29",
      "name": "Bahia"
    }
  },
  "profession": {
    "code": "7842",
    "title": "Alimentadores de linhas de produção"
  },
  "months": {
    "202501": {
      "admissions": 10,
      "dismissals": 4,
      "netBalance": 6,
      "totalTurnover": 14,
      "avgSalary": 1518.0,
      "salarySum": 15180.0,
      "salaryCount": 10
    },
    "202502": {
      "admissions": 0,
      "dismissals": 0,
      "netBalance": 0,
      "totalTurnover": 0,
      "avgSalary": 0.0,
      "salarySum": 0.0,
      "salaryCount": 0
    }
  }
}
```

The Lambda returns the same shape internally with snake_case fields. API Gateway
maps those response fields to camelCase for clients. Data availability failures
return `503`; unexpected failures return `500`.

Country queries read the 27 state aggregate items for each month. Missing state
records contribute zero, and country average salary is calculated from combined
`salarySum / salaryCount` across returned state records.

## Dataset catalog

The Lambda reads availability from one metadata item in `caged_dataset_catalog`:

```text
PK = DATASET#CAGED_GEO_JOB_METRICS
SK = METADATA
available_months = ["202604"]
latest_available_month = 202604
updated_at = 2026-06-25T21:00:00Z
```

The processing workflow can update this same item after a month is successfully
loaded. The planned metadata Lambda can read this item and adjacent catalog
items for professions and geographic selectors.

## Environment variables

```env
ENVIRONMENT=local
SOURCE_NAME=caged-query
METRICS_TABLE_NAME=caged_geo_job_metrics
DATASET_CATALOG_TABLE_NAME=caged_dataset_catalog
CBO_LOOKUP_TABLE_NAME=caged_cbo_lookup
CBO_FAMILY_CODE_INDEX_NAME=family_code-index
GEO_LOOKUP_TABLE_NAME=caged_geo_lookup
DATASET_ID=CAGED_GEO_JOB_METRICS
CORS_ALLOWED_ORIGIN=http://localhost:3000
MAX_QUERY_MONTHS=24
BATCH_GET_MAX_RETRIES=3
POWERTOOLS_SERVICE_NAME=caged-query
POWERTOOLS_LOG_LEVEL=INFO
POWERTOOLS_LOG_EVENT=false
```

Optional local DynamoDB configuration is supported through
`DYNAMODB_ENDPOINT_URL` or `AWS_ENDPOINT_URL_DYNAMODB`.

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

For local end-to-end execution, configure AWS credentials or a local DynamoDB
endpoint, seed the metric and catalog tables, then run:

```bash
uv run python debug_handler.py
```

The local runner defaults to DynamoDB Local at `http://127.0.0.1:8000` and uses
placeholder AWS credentials. Export a different `DYNAMODB_ENDPOINT_URL` before
running when another endpoint is required.

## Packaging

```bash
make package
```

This creates `dist/caged-query-lambda.zip` with
`handler.lambda_handler` as the entry point.

## Required infrastructure

Infrastructure remains in the global IaC repository. The Lambda role requires:

- `dynamodb:BatchGetItem` on `caged_geo_job_metrics`
- `dynamodb:GetItem` on `caged_dataset_catalog`
- `dynamodb:GetItem` on `caged_geo_lookup`
- `dynamodb:Query` on the `caged_cbo_lookup` `family_code-index` GSI

API Gateway should expose private read-only `GET /v1/metrics`, configure the
allowed frontend origin, add throttling and access logs, and invoke the Lambda
alias used by the deployment workflow.
