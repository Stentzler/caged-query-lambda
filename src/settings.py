import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    ENVIRONMENT: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "local"))
    SOURCE_NAME: str = field(
        default_factory=lambda: os.getenv("SOURCE_NAME", "boilerplate")
    )

    def __post_init__(self) -> None:
        if not self.ENVIRONMENT.strip():
            msg = "ENVIRONMENT must be configured"
            raise ValueError(msg)
        if not self.SOURCE_NAME.strip():
            msg = "SOURCE_NAME must be configured"
            raise ValueError(msg)
