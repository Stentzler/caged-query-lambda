import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    ENVIRONMENT: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "local"))
    SOURCE_NAME: str = field(
        default_factory=lambda: os.getenv("SOURCE_NAME", "caged-query")
    )
    METRICS_TABLE_NAME: str = field(
        default_factory=lambda: os.getenv("METRICS_TABLE_NAME", "caged_geo_job_metrics")
    )
    DATASET_CATALOG_TABLE_NAME: str = field(
        default_factory=lambda: os.getenv(
            "DATASET_CATALOG_TABLE_NAME", "caged_dataset_catalog"
        )
    )
    CBO_LOOKUP_TABLE_NAME: str = field(
        default_factory=lambda: os.getenv("CBO_LOOKUP_TABLE_NAME", "caged_cbo_lookup")
    )
    CBO_FAMILY_CODE_INDEX_NAME: str = field(
        default_factory=lambda: os.getenv(
            "CBO_FAMILY_CODE_INDEX_NAME", "family_code-index"
        )
    )
    GEO_LOOKUP_TABLE_NAME: str = field(
        default_factory=lambda: os.getenv("GEO_LOOKUP_TABLE_NAME", "caged_geo_lookup")
    )
    DATASET_ID: str = field(
        default_factory=lambda: os.getenv("DATASET_ID", "CAGED_GEO_JOB_METRICS")
    )
    CORS_ALLOWED_ORIGIN: str = field(
        default_factory=lambda: os.getenv("CORS_ALLOWED_ORIGIN", "*")
    )
    MAX_QUERY_MONTHS: int = field(
        default_factory=lambda: int(os.getenv("MAX_QUERY_MONTHS", "24"))
    )
    BATCH_GET_MAX_RETRIES: int = field(
        default_factory=lambda: int(os.getenv("BATCH_GET_MAX_RETRIES", "3"))
    )

    def __post_init__(self) -> None:
        required_values = {
            "ENVIRONMENT": self.ENVIRONMENT,
            "SOURCE_NAME": self.SOURCE_NAME,
            "METRICS_TABLE_NAME": self.METRICS_TABLE_NAME,
            "DATASET_CATALOG_TABLE_NAME": self.DATASET_CATALOG_TABLE_NAME,
            "CBO_LOOKUP_TABLE_NAME": self.CBO_LOOKUP_TABLE_NAME,
            "CBO_FAMILY_CODE_INDEX_NAME": self.CBO_FAMILY_CODE_INDEX_NAME,
            "GEO_LOOKUP_TABLE_NAME": self.GEO_LOOKUP_TABLE_NAME,
            "DATASET_ID": self.DATASET_ID,
            "CORS_ALLOWED_ORIGIN": self.CORS_ALLOWED_ORIGIN,
        }
        for name, value in required_values.items():
            if not value.strip():
                msg = f"{name} must be configured"
                raise ValueError(msg)

        if self.MAX_QUERY_MONTHS < 1:
            msg = "MAX_QUERY_MONTHS must be greater than zero"
            raise ValueError(msg)
        if self.BATCH_GET_MAX_RETRIES < 0:
            msg = "BATCH_GET_MAX_RETRIES cannot be negative"
            raise ValueError(msg)
