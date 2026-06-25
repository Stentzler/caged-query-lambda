# Boilerplate Lambda

Base template for CAGED Python Lambda repositories packaged as ZIP artifacts.

The template follows the same repository contract used by the project Lambdas:

- Python 3.14
- `uv` for dependency management
- `ruff` for linting and formatting
- `pytest` for tests
- `pre-commit` for local checks
- `debugpy` support for local debugging
- `serverless-toolkit` for shared Lambda utilities
- `make package` for the ZIP artifact consumed by `caged-lambda-cicd`

## Structure

```text
src/handler.py
src/service.py
src/settings.py
src/exceptions.py
tests/
events/
debug_handler.py
```

The IaC Lambda module defaults to `handler.lambda_handler`, so the production
entry point lives in `src/handler.py` and exposes both `handler` and
`lambda_handler`.

## Setup

```bash
uv sync --all-groups
uv run pre-commit install
```

## Environment Variables

Use `.env.example` as reference:

```env
ENVIRONMENT=local
SOURCE_NAME=boilerplate
POWERTOOLS_SERVICE_NAME=boilerplate
POWERTOOLS_LOG_LEVEL=INFO
POWERTOOLS_LOG_EVENT=false
```

Logging is handled by `serverless-toolkit`, which uses AWS Lambda Powertools to
generate structured JSON logs.

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Run the local Lambda runner with:

```bash
uv run python debug_handler.py
```

## Packaging

```bash
make package
```

The package target creates:

```text
dist/boilerplate-lambda.zip
```

When this template is copied for a real Lambda, rename the project, deployment
workflow values, function name, and ZIP artifact to match that Lambda.

## Deployment

The caller workflow uses:

```yaml
uses: Stentzler/caged-lambda-cicd/.github/workflows/lambda-python-zip.yml@main
```

The `zip_path` input must match the artifact created by `make package`.

## Notes

This repository should contain only Lambda application code. Infrastructure as
Code should live in the global IaC repository, and shared utilities should live
in `serverless-toolkit`.
