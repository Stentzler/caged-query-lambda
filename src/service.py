from typing import Any

from exceptions import InvalidBoilerplateEventError
from settings import Settings


class BoilerplateService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def execute(self, event: object) -> dict[str, Any]:
        if not isinstance(event, dict):
            raise InvalidBoilerplateEventError(
                "Boilerplate event must be a JSON object"
            )

        return {
            "status": "ok",
            "source": self.settings.SOURCE_NAME,
            "event": event,
        }
