# Project Architecture

## Overview

This repository is a boilerplate for one AWS Lambda packaged as a Python ZIP
artifact and deployed through the shared CAGED Lambda CI/CD workflow.

Follow the global `clean-code` skill for general implementation quality. The
rules below describe this repository's architecture and local conventions.

## Structure

- `src/handler.py`: Lambda entry point and dependency wiring. Keep it thin;
  delegate business behavior to the service.
- `src/service.py`: Application behavior for the Lambda.
- `src/settings.py`: Environment-backed runtime configuration.
- `src/exceptions.py`: Domain-specific exceptions and their context.
- `tests/`: Unit tests using fakes for Lambda dependencies.
- `events/`: Sample invocation payloads.
- `debug_handler.py`: Local Lambda runner with local defaults and a simulated
  Lambda context. Do not import it from production code.

## Shared Toolkit

Use `serverless-toolkit` for reusable, application-agnostic capabilities such
as AWS client/resource creation, logging, observability, and Lambda middleware.

Keep Lambda-specific business rules in the Lambda repository. Do not move domain
behavior into the toolkit merely to reduce a small amount of local code.

## Implementation Conventions

- Keep `handler.py` limited to dependency setup, logging, error boundaries, and
  invoking the service.
- Expose both `handler` and `lambda_handler = handler`; the IaC module defaults
  to `handler.lambda_handler`.
- Inject external dependencies into services when practical so tests do not
  require network or AWS access.
- Read configuration through `Settings`; avoid scattered environment lookups.
- Preserve the Lambda response contract unless a change is explicitly required.
- Add focused tests for new business rules and response fields.
- Do not add production behavior exclusively to `debug_handler.py`.

## Configuration Variables

Keep all runtime configuration in `src/settings.py` and mirror it in
`.env.example`, README documentation, and IaC environment variables.

Every Lambda should usually define:

- `ENVIRONMENT`: Current deployment environment, such as `local`, `dev`, or
  `prod`.
- `SOURCE_NAME`: Application/source identifier used by the Lambda.
- `POWERTOOLS_SERVICE_NAME`: Service name used in structured logs.
- `POWERTOOLS_LOG_LEVEL`: Logging level, usually `INFO`.
- `POWERTOOLS_LOG_EVENT`: Whether Lambda events are logged automatically.

If the Lambda uses S3 through `serverless-toolkit`, add only the variables the
Lambda actually needs:

- `S3_BUCKET_NAME`: Target or source bucket name.
- `S3_ENDPOINT_URL` or `AWS_ENDPOINT_URL_S3`: Optional local-development
  endpoint override. Leave unset in AWS.
- `S3_MAX_POOL_CONNECTIONS`: Optional boto3 connection-pool size.

If the Lambda uses DynamoDB through `serverless-toolkit`, add only the variables
the Lambda actually needs:

- `REGISTRY_TABLE_NAME` or a domain-specific table variable, such as
  `DYNAMODB_TABLE_NAME`: DynamoDB table name used by the Lambda.
- `REGISTRY_ID` or another domain-specific key variable when the Lambda reads a
  fixed registry/item.
- `DYNAMODB_ENDPOINT_URL` or `AWS_ENDPOINT_URL_DYNAMODB`: Optional
  local-development endpoint override. Leave unset in AWS.
- `DYNAMODB_MAX_POOL_CONNECTIONS`: Optional boto3 connection-pool size.

When adding S3 or DynamoDB access, also update the Lambda IaC with the matching
environment variables and least-privilege IAM permissions.

## Validation

Run before finishing code changes:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
make package
```

Use `uv run python debug_handler.py` for local end-to-end debugging when the
required local services are available.
