# AI core integration review

Implementation is confined to this independent `ai/` workspace. It uses the existing `setup/register/start/ask` vocabulary; no `llm.connect` API was introduced. No Git write, commit, push, or integration into the concurrent application was performed.

## Current release decision

The implementation is available for integration review. **Local generation quality is not accepted for production.** The 0.8B baseline exposed empty/weakly specified answers, and the 2B comparison still failed to express the Arabic refund request window accurately, even with a bilingual source. Its outputs, exact predicates, and nonzero quality-command outcome are retained. No larger untested model is presented as a proven solution.

Keep engineering checks and model quality as separate gates. The final native tests exercise the framework and lifecycle; they do not overturn the failed Arabic business case. Better model selection and a larger independently reviewed Arabic/English dataset remain necessary before deployment.

## Final measured results

- Full suite: **46 passed in 43.65 seconds**, including the native lifecycle test.
- Ruff: passed. Strict mypy: **298 source files passed**. Wheel: built and inspected; 318,309 bytes, typed, with core/usage metadata and no weights or caches.
- Verified cached payloads: runtime plus four model files; **all SHA-256 digests and byte counts match**.
- Cleanup: **zero owned native processes and zero partial download files** remaining.
- Core diff against the copied baseline: **29 added Python files, 22 modified, zero removed**, across the nine affected domains.
- Exact hybrid search: 1000 records × 1024 dimensions, 100 measured queries, **p50 27.57 ms / p95 43.02 ms**.
- Warm short generation: 0.8B **p95 244.27 ms**; 2B **p95 556.22 ms**, each over 20 repeated READY requests. These timings do not describe full RAG answers.
- In the separate 2B benchmark run, two-text embeddings had **p95 389.49 ms**, and two-document dedicated reranking **p95 591.12 ms**. All native benchmark assertions passed.
- **Business quality remains rejected:** the Arabic case failed for English-only and bilingual sources. The English case passed the narrow predicates. Failed gates are preserved, not relabeled as success.

## Acceptance scope

| Capability | Evidence | Assessment |
|---|---|---|
| Verified local model/runtime installation | Real model downloads through `Local.start`; HTTP concurrency/corruption/cancellation tests | Implemented and exercised; SHA/size pins and HTTPS provenance are not a native-code sandbox |
| Local generation, embeddings, dedicated reranking | `local-smoke.json`, `bench-local.json`, live lifecycle test | Real native inference on CPU; exact model names/revisions are in each result |
| Start/restart/close and stream interruption | Native model test including concurrent start, aborted stream, context overflow, restart, compaction | Tested on Ubuntu WSL; no Windows-native runtime claim |
| Sessions, rules, persistence, compaction | HTTP transaction tests, independent stores sharing one directory, native compaction/restore | Atomic local publication and serialized turns; no distributed transaction with an upstream LLM |
| Provider capability/options contracts | HTTP fixture tests for OpenAI, Claude, Gemini, DeepSeek, compatible routes | Request/response mapping tested; live remote acceptance is pending credentials |
| Harness and privacy | Unicode injection cases, PII redaction, monotonic limits, binary-redaction rejection | Useful bounded controls; heuristic detection is bypassable and not a complete injection defense |
| File extraction | Real PDF worker, resource bounds, content signatures, symlink/root rejection | UTF-8/text PDF accepted; empty PDF requires explicit OCR converter |
| Images/audio/video/PDF transcription | Typed converter plus multimodal HTTP fixture tests | Transport contracts only; no live remote OCR/ASR/video quality acceptance |
| Scoped ingestion/reindex/snapshots | Failed reindex retains previous data; duplicate/reference/scope corruption rejected | In-memory index transaction and validated snapshots; not a distributed vector database |
| Context and citations | Structured context, source-ID constraints, missing/invalid citation regression tests | Provenance membership is enforced; factual entailment requires separate quality evaluation |
| Generative ranking and evaluation | Actual local model runs in `usage.support` | Functional path accepted; judge scores are uncalibrated model opinions |
| Retrieval metrics | Known-value recall/MRR/NDCG tests | Correct binary relevance calculations; the two-question toy fixture is not a production retrieval benchmark |
| Package | Built wheel, inspected contents in `wheel.json` | Core and usage metadata included; Linux/WSL is the supported execution environment |

## Reproducible evidence

- `tests-final.txt`: complete suite, including the native test, at the recorded code state.
- `ruff-final.txt`, `mypy-final.txt`: lint and strict type checking across the copied core, tests, usages, and benches.
- `build.txt`, `wheel.json`: package build and content inspection.
- `local-smoke.json`: actual generation, 1024-dimensional embeddings, and raw reranking scores.
- `local-rag.json`, `rag-2b.json`: business scenario outputs, citations, quality predicates, and model judgments. Read the actual answers.
- `bench-local.json`: raw latency samples, model revisions, startup costs, throughput, and process RSS observations.
- `bench-primitives.json`: 100 queries over 1000 records with **1024-dimensional vectors**, plus PII redaction samples.
- `changes.json`: added/modified core files against the copied starting baseline; independent of Git and concurrent work.
- `verification.json`: final commands, outcomes, and resource/asset verification.

Intermediate diagnostics are retained deliberately. `local-first-attempt.json`, `schema-diagnostic.json`, `local-rag-incomplete-unit.json`, and `local-rag-missing-citation.json` are **failed or incomplete earlier evidence**, not final acceptance. The rag-2b-language-miss and rag-2b-unsupported-detail reports retain later quality failures; an early accepted=true predates the language check and is not the final quality verdict. `search-1024-before.json` is an exploratory timing that may have overlapped native work; do not use it for a controlled speedup claim. Files ending in `current` or `initial` can contain superseded failures.

The final 2B quality results are in evidence/rag-2b.json and evidence/rag-bilingual.json. The separate performance comparison is evidence/bench-2b.json. Neither a fast response nor a high judge score overrides accepted=false.

## Benchmark interpretation

The native benchmark makes 20 serial requests after one warmup per model, with two CPU threads and the native prompt cache enabled. Generation repeats a two-token READY response. Embeddings use two short texts; reranking compares two short passages. These are measured warm smoke workloads, not full-length answer throughput, concurrent capacity, or a production tail-latency SLO. P99 is descriptive interpolation over only 20 samples.

Cached startup includes digest verification, runtime verification, process startup, and health readiness. It is not first-download latency. Child max RSS is a per-child high-water observation, not the sum of simultaneous model memory.

The search benchmark is a synthetic numerical/lexical workload with realistic vector dimensionality. It measures exact search and fusion; it does not establish embedding relevance or retrieval quality on customer documents. The optimization caches validated normalized vectors at ingestion and uses the standard library's native sum-of-products operation. Tests compare rankings and scores against the scalar cosine reference, including replacement and clear.

The declared latency budgets are regression guardrails for this laptop workload, not enterprise service promises. Measurements can vary with the user's other sessions, CPU throttling, filesystem cache, and runtime versions.

## Corrections found by real execution

- The first local generation spent its budget without visible text. The selected Qwen runtime profile now disables thinking for these bounded smoke workloads.
- The pinned llama.cpp build requires the nested `json_schema.schema` response-format shape. A superficially successful completion had ignored the earlier request shape; real RAG exposed it and the adapter was corrected.
- Session mutation initially risked lost updates after replacing a cached session object. Lock identity and rereading state inside the transaction are now tested.
- A model override on dedicated embedding/ranking could disappear. Unsupported generation/session/file settings and dedicated instruction variants now fail explicitly.
- Nested JSON Schema references, runtime cache additions/hardlink tampering, and inconsistent snapshot references now have rejecting tests.
- Bare-number Arabic answers and empty citation arrays exposed weak acceptance criteria. The business scenario now tests the response language, unit, meaning of a request window, absence of invented processing claims, and citation relevance; RAG requires at least one permitted citation.
- A two-dimensional search timing was not representative of the actual embedder. The final primitive bench uses 1024 dimensions and retains raw samples.

## Integration notes

Review the nine affected domains together: `llm`, `rag`, `net`, `fs`, `thread`, `string`, `number`, `array`, `json`. Public exports, strict typing stubs, dependency/lock changes, and tests are part of the change. Compare manually against the other session's newer core; this workspace's baseline is only the copied starting point.

The application's bootstrap check is not present here. The independent architecture tests cover the new domains' ownership and import cycles, but integration still needs the application's own bootstrap gate.

The added narrow lint exceptions cover same-class private cloning/factory initialization, cleanup on startup failure, and small asynchronous temporary-file assertions. Three copied files had existing intentional callback/unused-argument/transliteration patterns; their exceptions are localized in `pyproject.toml`. The copied date parser's timezone warning is localized because the method attaches its configured timezone after parsing. No whole-project type or lint disable was added.

## Practical next acceptance work

1. Choose a larger or remote generator within an explicit latency/RAM/cost budget; preserve the failed Arabic cases as regressions.
2. Evaluate more independent cases, including unsupported questions, conflicting sources, procedural boundaries, Arabic paraphrases, and citation precision. Do not reuse the judge's opinion as ground truth.
3. Obtain live remote-provider and actual media/OCR/ASR evidence for the chosen providers and document classes.
4. Run sustained concurrency and recovery testing in the deployment environment after manual integration and application bootstrap checks.

## Remaining acceptance boundaries

This is an implemented and measured foundation ready for code review, not a blanket production certification. Remote providers, real media understanding, broad Arabic/domain quality, adversarial injection corpora, sustained concurrency, crash/power-loss campaigns, and multi-host persistence have not been accepted by this run. The copied core's unrelated domains have static checks but are not exhaustively runtime-tested here.

The application must provide authentication/tenant ownership, data retention/encryption policy, model licensing decisions, task-specific quality datasets, and any transactional outbox needed to connect its own database changes with external jobs. Those business responsibilities are not silently absorbed by the engine.
