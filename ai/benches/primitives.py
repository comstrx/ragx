from core.array import Search, SearchItem
from core.date import date
from core.error import Code, Fault
from core.fs import fs
from core.number import number
from core.string import safety
from core.thread import thread
import platform, resource

async def main () -> None:

    search = Search("synthetic-fixture-v1")
    search.upsert([
        SearchItem(str(index), "public", f"Product {index} refund policy",
                   tuple(float((index * 97 + column * 31) % 257 - 128) / 128 for column in range(1024)))
        for index in range(1000)
    ])
    query = tuple(float(column % 31 - 15) for column in range(1024))
    timings: list[float] = []
    total = date.tick()
    for _ in range(5): search.hybrid("refund policy", query, "public", 10)
    for _ in range(100):
        started = date.tick()
        results = search.hybrid("refund policy", query, "public", 10)
        if len(results) != 10: raise Fault(Code.INTERNAL, reason="bench.result")
        timings.append(date.elapsed(started))

    privacy: list[float] = []
    for _ in range(100):
        started = date.tick()
        clean = safety.redact("Contact alice@example.com or +201001234567. https://example.com")
        if "alice@" in clean: raise Fault(Code.INTERNAL, reason="bench.redaction")
        privacy.append(date.elapsed(started))

    duration = date.elapsed(total)
    report = {
        "kind": "CPU primitives; no inference or network", "python": platform.python_version(),
        "search": {"documents": 1000, "dimensions": 1024, "concurrency": 1, "warmup": 5, "samples": 100,
                   "samples_ms": timings, "p50_ms": number.percentile(timings, 50),
                   "p95_ms": number.percentile(timings, 95),
                   "p99_ms": number.percentile(timings, 99), "ops_per_second": 100000 / sum(timings)},
        "privacy": {"samples": 100, "samples_ms": privacy, "p50_ms": number.percentile(privacy, 50),
                    "p95_ms": number.percentile(privacy, 95), "p99_ms": number.percentile(privacy, 99)},
        "errors": 0, "total_ms": duration, "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "budgets": {"search_p95_ms": 250.0, "privacy_p95_ms": 50.0},
    }
    await fs.write_json("evidence/bench-primitives.json", report)
    if number.percentile(timings, 95) > 250 or number.percentile(privacy, 95) > 50:
        raise Fault(Code.INTERNAL, reason="bench.budget")

if __name__ == "__main__":

    thread.run(main())
