from collections.abc import Mapping
from typing import Any
from core.error import Code, Fault
from core.fs import Artifact, fs
from .model import LocalModel, Source

class Catalog:

    def source ( self, data: Mapping[str, Any] ) -> Source:

        for name in ("url", "file", "sha256", "revision"):
            if not isinstance(data.get(name), str) or not data[name]:
                raise Fault(Code.VALIDATION, reason=f"llm.catalog.{name}")
        if type(data.get("size")) is not int: raise Fault(Code.VALIDATION, reason="llm.catalog.size")

        return Source(data["url"], Artifact(data["sha256"], data["size"], data["file"]), data["revision"])

    async def load ( self, path: str, cache: str = ".runtime/models", threads: int = 2 ) -> dict[str, LocalModel]:

        data = await fs.read_json(path)
        if not isinstance(data, dict) or not isinstance(data.get("runtime"), dict):
            raise Fault(Code.VALIDATION, reason="llm.catalog.runtime")
        if not isinstance(data.get("models"), dict): raise Fault(Code.VALIDATION, reason="llm.catalog.models")
        runtime = self.source(data["runtime"])
        result: dict[str, LocalModel] = {}

        for role, entry in data["models"].items():
            if not isinstance(entry, dict) or entry.get("purpose") not in ("generate", "embed", "rank"):
                raise Fault(Code.VALIDATION, reason="llm.catalog.purpose")
            if not isinstance(entry.get("name"), str) or not entry["name"]:
                raise Fault(Code.VALIDATION, reason="llm.catalog.name")
            result[role] = LocalModel(
                self.source(entry), runtime, entry["name"], purpose=entry["purpose"], path=cache,
                threads=threads, context=2048, batch=512, embedding_format=entry.get("embedding_format", "plain"),
            )

        return result
