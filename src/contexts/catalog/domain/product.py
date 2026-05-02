from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from contexts.catalog.domain.exceptions import InvalidProductError

_MAX_SKU_LENGTH = 64
_MAX_NAME_LENGTH = 200
_CURRENCY_LENGTH = 3


@dataclass(frozen=True, slots=True)
class Product:
    id: UUID
    sku: str
    name: str
    price_cents: int
    currency: str
    created_at: datetime

    def __post_init__(self) -> None:
        _validate_sku(self.sku)
        _validate_name(self.name)
        _validate_price(self.price_cents)
        _validate_currency(self.currency)

    @classmethod
    def create(
        cls,
        *,
        sku: str,
        name: str,
        price_cents: int,
        currency: str = "EUR",
        product_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> Product:
        return cls(
            id=product_id or uuid4(),
            sku=sku.strip(),
            name=name.strip(),
            price_cents=price_cents,
            currency=currency.upper(),
            created_at=created_at or datetime.now(timezone.utc),
        )

    def with_changes(
        self,
        *,
        name: str | None = None,
        price_cents: int | None = None,
        currency: str | None = None,
    ) -> Product:
        return replace(
            self,
            name=name.strip() if name is not None else self.name,
            price_cents=price_cents if price_cents is not None else self.price_cents,
            currency=currency.upper() if currency is not None else self.currency,
        )


def _validate_sku(value: str) -> None:
    stripped = value.strip()
    if not stripped:
        raise InvalidProductError("sku must not be empty")
    if len(stripped) > _MAX_SKU_LENGTH:
        raise InvalidProductError(f"sku must be at most {_MAX_SKU_LENGTH} characters")


def _validate_name(value: str) -> None:
    stripped = value.strip()
    if not stripped:
        raise InvalidProductError("name must not be empty")
    if len(stripped) > _MAX_NAME_LENGTH:
        raise InvalidProductError(f"name must be at most {_MAX_NAME_LENGTH} characters")


def _validate_price(value: int) -> None:
    if value < 0:
        raise InvalidProductError("price_cents must not be negative")


def _validate_currency(value: str) -> None:
    if len(value) != _CURRENCY_LENGTH or not value.isalpha():
        raise InvalidProductError("currency must be a 3-letter ISO 4217 code")
