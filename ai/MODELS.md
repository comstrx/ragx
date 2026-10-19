# Local model and dependency decisions

Checked on 2026-10-19. Exact model revisions, SHA-256 digests, byte counts, and source URLs are stored in `src/usage/models.json`. The catalog is data; the core performs installation.

## Hardware and execution budget

The inspected machine has an Intel i5-10210U (4 cores/8 logical CPUs, AVX2), approximately 14 GiB visible to WSL, and an NVIDIA MX130 with 2 GiB VRAM and driver 472.19. About 11 GiB of WSL RAM was available at initial inspection.

This experiment uses CPU inference with two threads, one inference operation at a time, context 2048, and batch 512. Native smoke/benchmark stages unload a model before loading the next. RAG can hold several idle providers while executing stages sequentially. CUDA was not installed or enabled. These settings prioritize coexistence with the user's other sessions.

## Selected artifacts

| Role | Artifact | Weight bytes | Rationale |
|---|---|---:|---|
| Generation / chat / model evaluation | ggml-org Qwen3.5-0.8B, Q4_0 GGUF | 563,036,064 | Small CPU smoke baseline; multilingual generation and structured output within a modest memory budget |
| Embeddings | Qwen3-Embedding-0.6B, Q8_0 GGUF | 639,150,592 | Official Qwen quantization; multilingual 1024-dimensional embeddings; explicit Qwen query instruction format |
| Dedicated reranking | GPUStack bge-reranker-v2-m3, Q8_0 GGUF | 635,676,416 | Native llama.cpp reranking support, multilingual model, manageable CPU footprint |
| Runtime | llama.cpp stable v0.7.0 pointing to b11669 Ubuntu x64 | 17,851,611 | Prebuilt official runtime, avoiding an unproven Python-extension build on Python 3.15 |

The reranker GGUF is converted/published by GPUStack, not by BAAI. Its pinned hash proves identity relative to the selected artifact metadata; it does not establish formal provenance of the original training process or absence of native parser vulnerabilities.

These are resource-conscious trial models, not a claim that a 0.8B model is the most capable model the machine could ever run. Larger weights might fit RAM but would need separate latency/quality acceptance under concurrent workloads. The local suite does not establish Arabic domain expertise, broad hallucination resistance, or enterprise answer quality.

Primary sources:

- [Generation model card](https://huggingface.co/ggml-org/Qwen3.5-0.8B-GGUF)
- [Official embedding model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF)
- [Reranker conversion and files](https://huggingface.co/gpustack/bge-reranker-v2-m3-GGUF)
- [Stable llama.cpp release](https://github.com/ggml-org/llama.cpp/releases/tag/v0.7.0)
- [Pinned native runtime build](https://github.com/ggml-org/llama.cpp/releases/tag/b11669)
- [Server contract and supported rerankers](https://github.com/ggml-org/llama.cpp/blob/b11669/tools/server/README.md)
- [Pinned implementation of JSON response formats](https://github.com/ggml-org/llama.cpp/blob/b11669/tools/server/server-common.cpp)

## Additional 2B candidate: tested and rejected by the Arabic quality gate

The same DSL downloaded and ran [Unsloth Qwen3.5-2B Q4_K_M](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF), derived from [Qwen's base release](https://huggingface.co/Qwen/Qwen3.5-2B). The candidate is 1,280,835,840 bytes, revision f6d5376be1edb4d416d56da11e5397a961aca8ae, SHA-256 aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223. Its catalog is src/usage/candidate.json.

Initial acquisition and startup took approximately 403 seconds on this connection. Observed generation-process RSS was approximately 2 GiB. It improved relevance and source selection over the small smoke baseline, but still failed the strict Arabic request-window criterion, including a trial with an authoritative bilingual source. It is **not promoted to a production model**. Both catalogs remain trial configurations. The English case passed the stated narrow checks.

Do not replace the failed acceptance result with the model judge's high score. Earlier runs show why that score cannot serve as the only gate. The small fixture's lexical checks and manual inspection are useful regression checks, not comprehensive language or entailment evaluation.

## Installation and lifecycle

`Local.start` delegates downloads to `core.net.Downloads` and persistence to `core.fs.Artifacts`. Installation checks the declared byte count and SHA-256 digest before atomically publishing a file. It serializes concurrent installation with Linux file locks, cleans cancelled partials, and repairs a corrupt weight cache. Extraction checks traversal, unsafe links, sizes/member counts, and verifies cached runtime members against the archive, including unexpected added files.

Downloads use an explicit HTTPS host allowlist, public-address validation, DNS pinning, revalidated redirects, default certificate verification, and no inherited proxy environment. No arbitrary model Python code is executed; model payloads are GGUF. The runtime is nevertheless trusted native executable code.

The runtime runs as an owned loopback-only child process with a random API key, a minimal environment, no web UI, and no GPU offload. `core.thread.Process` owns termination of its process group. No machine-wide service or model manager was installed.

Idempotent cache reuse still verifies hashes when opening stopped providers; it is intentionally not a blind existence check. Repeated `start` on an already running provider returns immediately. There is no partial HTTP range resume: interrupted downloads restart on the next attempt. Acquisition is bounded by download/lock/startup policies.

## Libraries

New specialized dependencies selected from their official documentation/release metadata and locked with uv:

| Library | Locked version | Use |
|---|---|---|
| anyio | 4.15.1 | Async artifact I/O, cancellation, file locks |
| filetype | 1.2.0 | Content signatures |
| pypdf | 6.21.1 | Text-based PDF parsing in a bounded worker |
| regex | 2026.9.29 | Unicode matching with time limits |
| phonenumbers | 9.0.41 | Phone-number parsing and validity |
| RapidFuzz | 3.14.6 | Specialized edit-distance implementation |
| jsonschema | 4.26.0 | Draft 2020-12 validation behind a restricted core-owned Shape |

The copied core's HTTPX 0.28.1 remains the transport implementation behind `core.net`. No LLM SDK leaks into the application API. Optional full-document systems and large torch stacks were not installed just to provide nominal feature coverage.

References: [AnyIO](https://anyio.readthedocs.io/en/stable/), [filetype](https://github.com/h2non/filetype.py), [pypdf extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html), [regex](https://pypi.org/project/regex/), [phonenumbers](https://github.com/daviddrysdale/python-phonenumbers), [RapidFuzz](https://rapidfuzz.github.io/RapidFuzz/), [jsonschema](https://python-jsonschema.readthedocs.io/en/stable/validate/).

## Remote provider contracts

The OpenAI adapter now maps the core token budget to `max_completion_tokens`. The Gemini adapter retains the documented GenerateContent transport and its JSON-schema field; migration to the newer response-format transport is separate from this compatibility adapter. Claude native schema output is deliberately not advertised by this implementation. Client-validated schemas permit RAG with text-capable adapters without claiming provider-side constrained decoding. DeepSeek native JSON mode remains distinct from native JSON Schema.

Sources: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [Gemini GenerateContent](https://ai.google.dev/api/generate-content), [Claude structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [DeepSeek JSON mode](https://api-docs.deepseek.com/guides/json_mode/).

Remote account access, model availability, quotas, and real media quality were not tested without credentials. HTTP fixtures validate our mapping and normalization, not the provider's production service.
