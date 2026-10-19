from core.llm import Catalog, LocalModel

async def selected () -> dict[str, LocalModel]:

    return await Catalog().load("src/usage/models.json")
