from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from contexts.catalog.application.dtos import ProductDTO


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique stock-keeping unit identifier.",
        examples=["WIDGET-001"],
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable product name.",
        examples=["Blue widget"],
    )
    price_cents: int = Field(
        ...,
        ge=0,
        description="Price in the smallest currency unit (e.g. cents).",
        examples=[1999],
    )
    currency: str = Field(
        default="EUR",
        min_length=3,
        max_length=3,
        description="ISO 4217 three-letter currency code.",
        examples=["EUR"],
    )


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Updated product name. Omit to keep unchanged.",
        examples=["Updated widget"],
    )
    price_cents: int | None = Field(
        default=None,
        ge=0,
        description="Updated price in the smallest currency unit. Omit to keep unchanged.",
        examples=[2999],
    )
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Updated ISO 4217 currency code. Omit to keep unchanged.",
        examples=["USD"],
    )


class ProductResponse(BaseModel):
    id: UUID
    sku: str
    name: str
    price_cents: int
    currency: str
    created_at: datetime

    @classmethod
    def from_dto(cls, dto: ProductDTO) -> ProductResponse:
        return cls(
            id=dto.id,
            sku=dto.sku,
            name=dto.name,
            price_cents=dto.price_cents,
            currency=dto.currency,
            created_at=dto.created_at,
        )
