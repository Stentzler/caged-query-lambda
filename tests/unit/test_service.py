import pytest

from exceptions import InvalidBoilerplateEventError
from service import BoilerplateService
from settings import Settings


def test_execute_returns_boilerplate_response() -> None:
    service = BoilerplateService(settings=Settings(SOURCE_NAME="boilerplate-test"))

    response = service.execute({"hello": "world"})

    assert response == {
        "status": "ok",
        "source": "boilerplate-test",
        "event": {"hello": "world"},
    }


def test_execute_rejects_non_object_event() -> None:
    service = BoilerplateService(settings=Settings(SOURCE_NAME="boilerplate-test"))

    with pytest.raises(InvalidBoilerplateEventError, match="JSON object"):
        service.execute(["not", "an", "object"])
