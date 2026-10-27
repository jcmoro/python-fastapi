from contexts.assistant.ui.dependencies import get_embedding_client

WARM_UP_TEXT = "warm-up"


async def warm_up_embeddings() -> None:
    await get_embedding_client().embed([WARM_UP_TEXT])
