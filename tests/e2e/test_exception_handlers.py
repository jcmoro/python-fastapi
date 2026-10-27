import pytest
from fastapi.testclient import TestClient
from main import create_app

from shared.domain.errors import (
    ConflictError,
    DomainError,
    InvalidInputError,
    NotFoundError,
    ServiceUnavailableError,
)


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (NotFoundError, 404),
        (ConflictError, 409),
        (InvalidInputError, 422),
        (ServiceUnavailableError, 503),
    ],
)
def test_domain_error_maps_to_status_code(error: type[DomainError], status_code: int) -> None:
    application = create_app()

    @application.get("/raise")
    async def raise_error() -> None:
        raise error("something happened")

    with TestClient(application) as client:
        response = client.get("/raise")

    assert response.status_code == status_code
    assert response.json() == {"detail": "something happened"}
