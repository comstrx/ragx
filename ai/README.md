# RagX AI core

An independent integration workspace for the copied core. All implementation, dependencies, model assets, tests, benchmarks, and evidence live under `ai/`. This project uses Python 3.15 and Ubuntu Linux/WSL. It is intended for manual integration; it does not modify the application or deployment projects.

## Run

Run these commands from this directory:

```bash
export UV_CACHE_DIR="$PWD/.cache/uv"
export UV_PYTHON_DOWNLOADS=never
uv sync --frozen
uv run --frozen ruff check
uv run --frozen mypy
uv run --frozen pytest -q
uv run --frozen pytest -q --live
uv run --frozen python -m usage.local
uv run --frozen python -m usage.support
uv run --frozen python benches/primitives.py
uv run --frozen python benches/local.py
uv run --frozen python -m usage.compare
uv run --frozen python -m usage.bilingual
uv run --frozen python benches/local.py --catalog src/usage/candidate.json --output evidence/bench-2b.json
```

The native runtime smoke suite can pass while business answer quality fails. At the recorded state, usage.support / usage.compare / usage.bilingual are strict quality experiments, not promised green demonstrations. The 2B Arabic cases deliberately return a nonzero exit code and persist accepted=false when the requested meaning is lost. See REVIEW.md before interpreting a model judge score.

Run native inference commands sequentially. The ordinary tests do not download models. The `--live` suite and usage/benchmark commands can download the pinned runtime and models **through the core DSL** when their verified cache is absent. Model assets live in `.runtime/models`; dependencies in `.venv`; uv's cache in `.cache/uv`. These generated directories are ignored.

## LLM DSL

```python
from core.llm import Catalog, Harness, Llm

engine = Llm()
engine.setup(path=".runtime/conversations")
models = await Catalog().load("src/usage/models.json")
engine.register(models["generation"], name="writer", default=True)
engine.register(models["embedding"], name="vectors")
engine.register(models["ranking"], name="ranker")

try:
    await engine.start("writer")
    chat = engine.use("writer").temperature(0).harness(
        Harness(instructions=("Answer accurately and concisely.",)),
    ).session(name="Customer support")
    reply = await chat.ask("Explain retrieval augmented generation.")
    session_id = chat.session_id()
    if session_id is not None:
        restored = await engine.restore(session_id)
        follow_up = await restored.ask("Give one example.")
finally:
    await engine.close()
```

There is no `llm.connect`. `register` accepts either a provider or a core-owned `LocalModel`. It performs no download. `start` acquires resources; it is idempotent while running. Local operations may start their provider automatically. Call `start` explicitly to separate first-time installation from the inference timeout.

The owner can set the root policy with Llm.setup(harness=Harness(...)); request policies can only tighten it. For RAG, Policies.common defines the stage ceiling and unspecified stage policies inherit it. Fluent prompt operations return independent copies. `system` replaces the prompt's system setting; `instruct` appends instructions. Session rules are preserved when a resumed request supplies additional instructions. `harness` composes restrictions monotonically: minimum limits, combined instructions, and privacy/injection flags that cannot be relaxed by a later policy.

`embed(texts, EmbeddingOptions(...))` and `rank(query, documents, RankingOptions(...))` are separate typed operations. Dedicated operations reject generation/session/file options and unsupported instructions. Register a separate provider for a separate embedding model; changing `Prompt.model` is not a way to silently change an embedding space.

`RankingOptions(method="generation", native_schema=True)` uses the selected generation provider to score documents through the same `ask` contract. Dedicated reranker scores are model-specific raw scores, not calibrated probabilities. Generative scores are constrained to [0, 1], but remain model judgments.

`schema(shape)` requires native schema capability and validates the final result again locally. `schema(shape, native=False)` explicitly sends a schema instruction and validates the returned JSON locally; it does not promise constrained decoding. Use this explicit alternative for an adapter without native schema support. `json()` requests the provider's native JSON mode.

Remote adapters: `ChatGpt`, `Claude`, `Gemini`, `DeepSeek`, and `Compatible`. Caller-selected model availability is still an upstream contract. `Compatible(..., capabilities=Capabilities(embed=True, ...))` supports explicitly declared compatible servers. OpenAI embedding models are registered with their own `text-embedding-...` model identifier. Native Claude schema output is not implemented in this adapter; client-validated output is available.

## Sessions and effects

- A completed validated answer and its user turn are saved together after inference. A failed response, invalid schema, cancelled stream, or incomplete stream does not save a partial turn.
- Stream chunks are provisional. The single final `done=True` event follows validation and session persistence. Close abandoned streams, for example with `contextlib.aclosing`.
- Durable sessions use private files, atomic replace, file/directory fsync, and a per-session Linux advisory lock. Independent stores share that lock. Memory-only sessions use a stable per-session mutex.
- The remote request and the session write are **not one distributed transaction**. A write failure or cancellation after an upstream side effect may leave that effect completed without a saved reply. There is no automatic repeat of a generation POST after uncertain completion.
- `compact(keep=...)` keeps a positive even number of recent messages, summarizes older text, and publishes the new summary only after a successful response. The summary is supplied later as untrusted conversation data. It is lossy, model-generated text; attachment content is not independently summarized.
- New sessions are memory-resident until the first successful turn or explicit `sessions.save`. The TTL controls the memory cache; durable records survive it until explicit deletion. `restore` loads a durable record; `resume` addresses a cached record.
- Session IDs and RAG scopes are application-supplied namespaces, not authorization checks. The application must derive them from authenticated ownership.
- `close` waits for queued/in-flight operations on a provider and then releases its HTTP client and owned child process. Cache files and stored sessions remain. A subsequent `start`/operation can reopen that provider. `forget` closes and unregisters it.
- Harness inference deadlines include provider queueing/startup, after the session transaction is acquired. Session file-lock waiting has its own bound. Timeout faults conservatively expose uncertain completion.
- Token estimates from `estimate_tokens` are character heuristics. The local adapter uses the actual runtime tokenizer to reject overflowing generation contexts and conservatively bounds embedding/rerank input against context and batch capacity.

## RAG DSL

```python
from core.fs import Part
from core.rag import Document, Models, Policies, Rag, RagOptions
from core.llm import Harness

rag = Rag(
    Models(
        generation=engine.use("writer"),
        embedding=engine.use("vectors"),
        ranking=engine.use("ranker"),
        evaluation=engine.use("writer"),
    ),
    Policies(generation=Harness(instructions=("Preserve facts and their units.",))),
    RagOptions(candidates=8, context_chars=6000),
)
await rag.ingest([
    Document("refund-policy", "policy.txt", (Part("Refunds are available for 14 days."),)),
], scope="authenticated-workspace")
answer = await rag.ask("What is the refund period?", scope="authenticated-workspace")
judgment = await rag.evaluate("What is the refund period?", answer)
await rag.save(".runtime/index.json")
```

An individual request can supply a configured generation Prompt through the generation parameter of rag.ask; stage harness restrictions still apply. Each stage accepts its own configured `Prompt`, provider, model, and harness. `Policies.common` combines with stage policies. Instructions that make sense for generation may not make sense for vector models: put them in the appropriate stage. Dedicated embeddings/reranking reject arbitrary prompt instructions rather than contaminating their inputs.

`files` routes content through `core.fs.Extraction`. `ingest` chunks through `core.string`, embeds through `core.llm`, and indexes through `core.array.Search`. All embeddings complete before replacement is committed. Reingestion replaces the old document's chunks atomically inside this in-memory index. It is not an application database transaction or an outbox.

Search combines exact cosine similarity, BM25, and reciprocal rank fusion. It is bounded in-memory search, not ANN or a distributed vector database. Scopes isolate retrieval. Snapshots validate embedding identity, dimensions, duplicate IDs, references, text spans, and scope consistency before replacing the current state. Filesystem ownership still matters: snapshots are not authenticated signatures.

Contexts use short request-local source labels such as S1 and S2 with provenance. Returned citations map back to the original stable passage IDs. Contexts encode source content as untrusted JSON data, and enforce a character budget. Answers require at least one citation drawn from the selected IDs, including a source explaining an evidence limitation. A valid citation does not prove that the answer is entailed by its source. Evaluation scores are model opinions; `core.array.ranking.metrics` computes recall, MRR, and binary NDCG against explicit relevance labels.

For remote providers without native schema support, set `RagOptions(native_schema=False)` to choose client validation explicitly. Empty/unusable context raises a fault rather than fabricating grounding.

## Capability ownership

| Domain | Added responsibility |
|---|---|
| `core.net` | HTTPS artifact downloads, validated redirects, DNS pinning, streaming transport |
| `core.fs` | Hash/size verification, atomic artifacts and records, runtime archives, file signatures, bounded text/PDF/media extraction |
| `core.thread` | Managed process groups, termination, mutexes, deadlines |
| `core.string` | Unicode normalization, bounded regex, PII spans/redaction, injection heuristics, chunks/token terms, fast edit distance |
| `core.number` | Finite vector validation, normalization, cosine, score math |
| `core.array` | Scoped exact search, BM25, RRF, labeled retrieval metrics |
| `core.json` | Core-owned JSON Schema validation without external references |
| `core.llm` | Provider semantics, capabilities, prompts, harness, sessions, local runtime orchestration, transcription |
| `core.rag` | Ingestion/retrieval/context/generation/evaluation orchestration and validated snapshots |
| `src/usage` | Business examples, model choices, acceptance questions, and expectations |

## Files, media, and privacy

Text is decoded strictly as UTF-8. File type is inspected from content, not the extension. Reads are bounded, reject nonregular files/final symlinks and executable signatures. An allowed root uses descriptor-relative traversal and rejects symlink ancestors. PDF parsing runs in a separate process with CPU/address-space/page/character limits. PDF JavaScript is not executed. This is process/resource isolation, not a container/seccomp security sandbox.

Text-based PDFs are tested with a real generated PDF. PDFs without extractable text require an explicit OCR converter; the parser does not silently accept an empty result. Images/audio/video use an explicitly supplied converter such as `llm.Transcriber`, which in turn uses a modality-capable prompt. Missing converters and unsupported file types produce explicit faults. Native OCR, speech recognition, and video understanding models are not installed or validated here.

Media adapters have HTTP contract tests with fixtures. They have **not** been accepted against live remote services. Binary media cannot be safely covered by a text-only redaction policy: such a request is rejected until text is extracted first.

`core.string.safety` detects/redacts emails, URLs, and phone numbers, including configurable phone regions. Injection detection is a bounded heuristic with English/Arabic patterns and Unicode normalization; it is not a complete security classifier. Retrieved text is never promoted to system authority. Prompts and model outputs still require application-level trust boundaries.

Harness redaction protects outgoing model text. It does not retroactively anonymize raw documents, index files, or the application's storage; explicitly redact before ingestion when privacy at rest is required. No provider tool execution, arbitrary code execution, or autonomous external actions are exposed by this DSL.

## Review and integration

Read `REVIEW.md`, `MODELS.md`, and `evidence/changes.json` before merging. The latter compares current Python sources with hashes of the copied starting core; it does not compare against the concurrent application's newer work.

Merge the changed core contracts and their tests together. Keep the application's newer independent changes. Do not copy `.runtime`, `.venv`, caches, or benchmark timings as production configuration. The independent package intentionally keeps dependencies needed by the entire copied core.

The repository application's `bootstrap check` module is absent in this independent project. Here, `tests/test_laws.py` checks new-domain ownership, dependency cycles, flat files, and source constraints; it does not claim to replace the application's bootstrap gate after integration.
