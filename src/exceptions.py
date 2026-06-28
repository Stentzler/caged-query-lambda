class InvalidMetricsQueryError(ValueError):
    """Raised when an API request does not match the metrics query contract."""


class DatasetCatalogUnavailableError(RuntimeError):
    """Raised when dataset availability metadata cannot be loaded."""


class MetricsDataUnavailableError(RuntimeError):
    """Raised when DynamoDB cannot return all requested metric records."""
