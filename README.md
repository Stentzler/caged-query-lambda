# CAGED Query Lambda

Read-only AWS Lambda used by the CAGED web application to retrieve monthly
geographic job metrics from DynamoDB.

The Lambda is packaged as a Python ZIP artifact and is designed for an API
Gateway HTTP API v2 Lambda proxy integration.

## API

### `GET /v1/metrics`

Query parameters:

| Parameter | Required | Description |
| --- | --- | --- |
| `locationType` | Yes | `COUNTRY`, `STATE`, or `CITY` |
| `locationCode` | State/city only | IBGE state or city code |
| `professionCode` | No | CBO family code; defaults to `ALL` |
| `from` | No | First month in `YYYYMM` format |
| `to` | No | Last month in `YYYYMM` format |

`from` and `to` must be supplied together. Without them, the API queries the
catalog's `latest_available_month`. The inclusive range is limited to 24 months
by default and must include at least one catalog `available_months` value.

Example:

```http
GET /v1/metrics?locationType=CITY&locationCode=292070&professionCode=7842&from=202501&to=202512
```

Successful responses contain an ordered `months` object:

```json
{
  "dataset": "CAGED_GEO_JOB_METRICS",
  "catalog_version": "2026-06-25T21:00:00Z",
  "query": {
    "location_type": "CITY",
    "location_code": "292070",
    "profession_code": "7842",
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
      "net_balance": 6,
      "total_turnover": 14,
      "avg_salary": 1518.0,
      "salary_sum": 15180.0,
      "salary_count": 10
    },
    "202502": {
      "admissions": 0,
      "dismissals": 0,
      "net_balance": 0,
      "total_turnover": 0,
      "avg_salary": 0.0,
      "salary_sum": 0.0,
      "salary_count": 0
    }
  }
}
```

Country queries attempt to read the 27 state aggregate items for each month.
Missing state records contribute zero. Country average salary is calculated from
the combined `salary_sum / salary_count` across returned state records.

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

API Gateway should expose public read-only `GET /v1/metrics`, configure the
allowed frontend origin, add throttling and access logs, and invoke the Lambda
alias used by the deployment workflow.
