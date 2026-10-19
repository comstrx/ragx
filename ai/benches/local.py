from core.date import date
from core.error import Code, Fault
from core.fs import fs
from core.llm import Catalog, Llm, Local
from core.number import number
from core.thread import thread
import argparse, platform, resource

SAMPLES = 20

async def main (
    catalog: str = "src/usage/models.json", output: str = "evidence/bench-local.json",
) -> None:

    selected_models = await Catalog().load(catalog)
    report: dict[str, object] = {
        "python": platform.python_version(), "concurrency": 1, "threads_per_model": 2, "samples": SAMPLES,
        "percentiles": "Linear interpolation over 20 samples; descriptive, not a production tail-latency estimate.",
        "models": {},
    }
    results: dict[str, object] = {}
    engine = Llm()
    try:
        for role, spec in selected_models.items():
            provider = Local(spec, name=role)
            engine.register(provider)
            started = date.tick()
            await engine.start(role)
            start_ms = date.elapsed(started)
            times: list[float] = []
            tokens: list[int] = []
            prompt = engine.use(role)
            for attempt in range(SAMPLES + 1):
                tick = date.tick()
                if role == "generation":
                    result = await prompt.max_tokens(16).temperature(0).ask("Reply with exactly READY.")
                    if result.text.strip() != "READY": raise Fault(Code.INTERNAL, reason="bench.generation")
                    count = result.usage.output
                elif role == "embedding":
                    embedded = await prompt.embed(["How do I reset my password?", "إعادة تعيين كلمة المرور"])
                    if len(embedded.vectors) != 2: raise Fault(Code.INTERNAL, reason="bench.embedding")
                    count = 0
                else:
                    ranked = await prompt.rank(
                        "reset password",
                        ["Use the account security page to reset your password.", "Fresh baked bread."],
                    )
                    if ranked[0].index != 0: raise Fault(Code.INTERNAL, reason="bench.ranking")
                    count = 0
                elapsed = date.elapsed(tick)
                if attempt:
                    times.append(elapsed)
                    tokens.append(count)
            await provider.close()
            budget = 15_000.0
            results[role] = {
                "model": spec.name, "revision": spec.source.revision, "sha256": spec.source.artifact.sha256,
                "start_cached_ms": start_ms, "warmup": 1, "samples_ms": times,
                "p50_ms": number.percentile(times, 50), "p95_ms": number.percentile(times, 95),
                "p99_ms": number.percentile(times, 99), "requests_per_second": SAMPLES * 1000 / sum(times),
                "output_tokens_per_second": sum(tokens) * 1000 / sum(times) if sum(tokens) else None,
                "errors": 0, "budget_p95_ms": budget,
            }
            report["models"] = results
            report["parent_max_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            report["completed_children_max_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            await fs.write_json(output, report)
            if number.percentile(times, 95) > budget: raise Fault(Code.INTERNAL, reason="bench.local.budget")
    finally: await engine.close()

if __name__ == "__main__":

    arguments = argparse.ArgumentParser()
    arguments.add_argument("--catalog", default="src/usage/models.json")
    arguments.add_argument("--output", default="evidence/bench-local.json")
    options = arguments.parse_args()
    thread.run(main(options.catalog, options.output))
