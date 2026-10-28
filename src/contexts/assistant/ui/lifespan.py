from contexts.assistant.ui.dependencies import (
    clear_anthropic_dependants,
    get_anthropic_client,
    get_embedding_client,
)

WARM_UP_TEXT = "warm-up"


async def warm_up_embeddings() -> None:
    await get_embedding_client().embed([WARM_UP_TEXT])


async def close_anthropic_client() -> None:
    if get_anthropic_client.cache_info().currsize:
        await get_anthropic_client().close()
    clear_anthropic_dependants()
