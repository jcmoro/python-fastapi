import asyncio
from contextlib import asynccontextmanager

from contexts.assistant.application.dtos import IndexReportDTO
from contexts.assistant.ui.dependencies import (
    get_catalog_reader,
    get_document_index,
    get_embedding_client,
    get_index_catalog_use_case,
)
from contexts.catalog.ui.dependencies import (
    get_get_product_use_case,
    get_list_products_use_case,
    get_product_repository,
)
from shared.infrastructure.database import engine, get_session


async def reindex() -> IndexReportDTO:
    async with asynccontextmanager(get_session)() as session:
        use_case = get_index_catalog_use_case(
            catalog_reader=get_catalog_reader(
                get_list_products_use_case(get_product_repository(session)),
                get_get_product_use_case(get_product_repository(session)),
            ),
            embedding_client=get_embedding_client(),
            document_index=get_document_index(session),
        )
        return await use_case.execute()


async def _main() -> None:
    try:
        report = await reindex()
    finally:
        await engine.dispose()
    print(f"indexed={report.indexed} unchanged={report.unchanged} deleted={report.deleted}")


if __name__ == "__main__":
    asyncio.run(_main())
