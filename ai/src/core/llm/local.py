from collections.abc import AsyncIterator, Sequence
from core.error import Code, Fault
from core.fs import Artifacts, Bundle
from core.net import Client, Downloads, net
from core.rand import rand
from core.thread import Process, thread
from .capability import Capabilities
from .compatible import Compatible
from .embedding import EmbeddingOptions, Embeddings, Score, scores
from .model import LocalModel
from .message import Chunk, Message, Options, Reply
from core.thread import Mutex
from dataclasses import replace
from typing import override

class Local(Compatible):

    name = "local"

    def __init__ ( self, spec: LocalModel, name: str = "local" ) -> None:

        super().__init__("", model=spec.name, retries=0)
        self.name = name
        self.spec = spec
        self._start_lock = Mutex()
        self._process: Process | None = None
        self._artifacts = Artifacts(spec.path)
        self.capabilities = Capabilities(
            generate=spec.purpose == "generate", stream=spec.purpose == "generate",
            embed=spec.purpose == "embed", rank=spec.purpose == "rank", json=spec.purpose == "generate",
            schema=spec.purpose == "generate",
            embedding_instruction=spec.purpose == "embed" and spec.embedding_format == "qwen3",
        )

    @override
    def ready ( self ) -> bool:

        return self._process is not None and self._process.running()

    @override
    def identity ( self ) -> str:

        return f"{self.spec.source.artifact.sha256}:{self.spec.runtime.artifact.sha256}:{self.spec.embedding_format}"

    @override
    async def start ( self ) -> None:

        async with self._start_lock:
            if self._process is not None and self._process.running(): return

            downloads = Downloads(self.spec.policy)
            model = await self._artifacts.install(
                self.spec.source.artifact, lambda: downloads.chunks(self.spec.source.url),
            )
            runtime = await self._artifacts.install(
                self.spec.runtime.artifact, lambda: downloads.chunks(self.spec.runtime.url),
            )
            root = self._artifacts.root / ("runtime-" + self.spec.runtime.artifact.sha256)
            bundle = Bundle()

            async with self._artifacts.lock(self.spec.runtime.artifact.sha256 + ".unpack"):
                await thread.offload(bundle.unpack, runtime, root)

            executable = await thread.offload(bundle.executable, root, "llama-server")
            port = net.free_port()
            self._key = rand.token(32)
            self._base = f"http://127.0.0.1:{port}/v1"
            await self._client.close()
            self._client = Client(self._base, wait=120.0, retries=0)
            command = [
                str(executable), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
                "-t", str(self.spec.threads), "-tb", str(self.spec.threads), "-c", str(self.spec.context),
                "-b", str(self.spec.batch), "-ub", str(self.spec.batch), "-np", "1", "-ngl", "0",
                "--no-warmup", "--no-webui", "--no-slots",
                "--chat-template-kwargs", '{"enable_thinking": false}',
                "--alias", self.model,
            ]
            if self.spec.purpose == "embed": command.extend(["--embedding", "--pooling", "last"])
            if self.spec.purpose == "rank": command.extend(["--embedding", "--reranking", "--pooling", "rank"])
            environment = {"LLAMA_API_KEY": self._key, "OMP_NUM_THREADS": str(self.spec.threads)}
            self._process = await Process.start(command, environment, inherit=False)

            try:
                if not await thread.poll(self._healthy, every=0.25, within=self.spec.startup):
                    raise Fault(Code.UNAVAILABLE, reason="llm.local.startup")
            except BaseException:
                await self._process.close()
                self._process = None
                await self._client.close()
                raise

    async def _healthy ( self ) -> bool:

        if self._process is None or not self._process.running():
            raise Fault(Code.UNAVAILABLE, reason="llm.local.exited")
        try:
            reply = await self._client.get("/../health", headers=self.headers(), wait=1.0)
            return reply.ok()
        except Fault: return False

    @override
    async def complete ( self, messages: Sequence[Message], options: Options ) -> Reply:

        self.capabilities.require("generate")
        await self.start()
        await self.validate_context(messages, options)
        return replace(await super().complete(messages, options), model=self.model)

    @override
    async def stream ( self, messages: Sequence[Message], options: Options ) -> AsyncIterator[Chunk]:

        self.capabilities.require("stream")
        await self.start()
        await self.validate_context(messages, options)
        async for chunk in super().stream(messages, options): yield chunk

    @override
    async def embed ( self, texts: Sequence[str], options: EmbeddingOptions ) -> Embeddings:

        self.capabilities.require("embed")
        await self.start()
        values = [f"Instruct: {options.instruction}\nQuery: {text}" for text in texts] if (
            options.query and options.instruction
        ) else list(texts)
        for value in values:
            if await self.tokens(value) + 2 > min(self.spec.context, self.spec.batch):
                raise Fault(Code.VALIDATION, reason="llm.embedding.context")
        data = await self.post("/embeddings", {"model": self.model, "input": values})
        return Embeddings.parse(data, len(texts), self.model, self.name)

    @override
    async def rank ( self, query: str, documents: Sequence[str] ) -> tuple[Score, ...]:

        self.capabilities.require("rank")
        await self.start()
        query_tokens = await self.tokens(query)
        for document in documents:
            if query_tokens + await self.tokens(document) + 4 > min(self.spec.context, self.spec.batch):
                raise Fault(Code.VALIDATION, reason="llm.ranking.context")
        data = await self.post("/rerank", {"model": self.model, "query": query, "documents": list(documents)})
        return scores(data, documents)

    async def validate_context ( self, messages: Sequence[Message], options: Options ) -> None:

        if options.model is not None and options.model != self.model:
            raise Fault(Code.VALIDATION, reason="llm.local.model")
        body = self.body(messages, options)
        formatted = await self.post("/../apply-template", {"messages": body["messages"]})
        count = await self.tokens(formatted["prompt"])
        if count + (options.max_tokens or 512) > self.spec.context:
            raise Fault(Code.VALIDATION, reason="llm.context.limit")

    async def tokens ( self, text: str ) -> int:

        await self.start()
        data = await self.post("/../tokenize", {"content": text})
        return len(data["tokens"])

    @override
    async def close ( self ) -> None:

        async with self._gate, self._start_lock:
            if self._process is not None:
                await self._process.close()
                self._process = None
            await self._client.close()

    def diagnostics ( self ) -> str:

        return self._process.output() if self._process is not None else ""
