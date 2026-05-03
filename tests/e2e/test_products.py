from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from httpx import AsyncClient

from contexts.catalog.domain.product import Product


class TestCreateProduct:
    async def test_returns_201_and_persisted_payload(self, async_client: AsyncClient) -> None:
        payload = {
            "sku": "SKU-1",
            "name": "Blue widget",
            "price_cents": 1999,
            "currency": "EUR",
        }

        response = await async_client.post("/products", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["sku"] == "SKU-1"
        assert body["name"] == "Blue widget"
        assert body["price_cents"] == 1999
        assert body["currency"] == "EUR"
        UUID(body["id"])  # parses
        assert body["created_at"]

    async def test_currency_defaults_to_eur(self, async_client: AsyncClient) -> None:
        payload = {"sku": "SKU-2", "name": "Widget", "price_cents": 100}

        response = await async_client.post("/products", json=payload)

        assert response.status_code == 201
        assert response.json()["currency"] == "EUR"


class TestGetProduct:
    async def test_returns_200_when_product_exists(
        self,
        async_client: AsyncClient,
        add_product: Callable[..., Awaitable[Product]],
    ) -> None:
        product = await add_product(sku="SKU-1", name="Widget", price_cents=999)

        response = await async_client.get(f"/products/{product.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(product.id)
        assert body["sku"] == "SKU-1"
        assert body["name"] == "Widget"

    async def test_returns_404_when_product_missing(self, async_client: AsyncClient) -> None:
        missing_id = uuid4()

        response = await async_client.get(f"/products/{missing_id}")

        assert response.status_code == 404
        assert str(missing_id) in response.json()["detail"]

    async def test_returns_422_for_malformed_uuid(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/products/not-a-uuid")

        assert response.status_code == 422


class TestErrorPaths:
    async def test_post_returns_409_on_duplicate_sku(
        self, async_client: AsyncClient
    ) -> None:
        payload = {"sku": "DUP-1", "name": "Widget", "price_cents": 100}
        first = await async_client.post("/products", json=payload)
        assert first.status_code == 201

        second = await async_client.post("/products", json=payload)

        assert second.status_code == 409
        assert "DUP-1" in second.json()["detail"]

    async def test_post_returns_422_when_field_missing(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.post("/products", json={"name": "X"})

        assert response.status_code == 422

    async def test_post_returns_422_on_negative_price(
        self, async_client: AsyncClient
    ) -> None:
        payload = {"sku": "SKU-X", "name": "Widget", "price_cents": -1}

        response = await async_client.post("/products", json=payload)

        assert response.status_code == 422

    async def test_post_returns_422_on_invalid_currency_format(
        self, async_client: AsyncClient
    ) -> None:
        # Pydantic accepts "1AB" (length 3); the domain rejects it (must be alpha).
        payload = {"sku": "SKU-Y", "name": "Widget", "price_cents": 100, "currency": "1AB"}

        response = await async_client.post("/products", json=payload)

        assert response.status_code == 422
        assert "currency" in response.json()["detail"].lower()

    async def test_post_returns_422_on_extra_field(self, async_client: AsyncClient) -> None:
        # Schema is configured with extra="forbid".
        payload = {
            "sku": "SKU-Z",
            "name": "Widget",
            "price_cents": 100,
            "unknown": "x",
        }

        response = await async_client.post("/products", json=payload)

        assert response.status_code == 422


class TestListProducts:
    async def test_returns_empty_list_when_no_products(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/products")

        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_seeded_products_in_creation_order(
        self,
        async_client: AsyncClient,
        seeded_products: list[Product],
    ) -> None:
        response = await async_client.get("/products")

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body] == [str(p.id) for p in seeded_products]

    async def test_paginates_with_limit_and_offset(
        self,
        async_client: AsyncClient,
        seeded_products: list[Product],
    ) -> None:
        response = await async_client.get("/products?limit=2&offset=2")

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body] == [str(p.id) for p in seeded_products[2:4]]

    async def test_returns_422_on_invalid_limit(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/products?limit=0")

        assert response.status_code == 422


class TestUpdateProduct:
    async def test_patches_provided_fields_only(
        self,
        async_client: AsyncClient,
        add_product: Callable[..., Awaitable[Product]],
    ) -> None:
        product = await add_product(sku="SKU-1", name="Widget", price_cents=100)

        response = await async_client.patch(
            f"/products/{product.id}",
            json={"name": "Gadget", "price_cents": 500},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Gadget"
        assert body["price_cents"] == 500
        assert body["sku"] == "SKU-1"

    async def test_returns_404_when_product_missing(
        self, async_client: AsyncClient
    ) -> None:
        missing_id = uuid4()

        response = await async_client.patch(
            f"/products/{missing_id}", json={"name": "X"}
        )

        assert response.status_code == 404

    async def test_returns_422_on_negative_price(
        self,
        async_client: AsyncClient,
        add_product: Callable[..., Awaitable[Product]],
    ) -> None:
        product = await add_product()

        response = await async_client.patch(
            f"/products/{product.id}", json={"price_cents": -1}
        )

        assert response.status_code == 422

    async def test_returns_422_on_extra_field(
        self,
        async_client: AsyncClient,
        add_product: Callable[..., Awaitable[Product]],
    ) -> None:
        product = await add_product()

        response = await async_client.patch(
            f"/products/{product.id}", json={"sku": "NEW-SKU"}
        )

        assert response.status_code == 422


class TestDeleteProduct:
    async def test_returns_204_and_removes_product(
        self,
        async_client: AsyncClient,
        add_product: Callable[..., Awaitable[Product]],
    ) -> None:
        product = await add_product()

        delete_response = await async_client.delete(f"/products/{product.id}")
        get_response = await async_client.get(f"/products/{product.id}")

        assert delete_response.status_code == 204
        assert get_response.status_code == 404

    async def test_returns_404_when_product_missing(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.delete(f"/products/{uuid4()}")

        assert response.status_code == 404
