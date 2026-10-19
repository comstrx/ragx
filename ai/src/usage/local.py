from core.date import date
from core.fs import fs
from core.llm import EmbeddingOptions, Llm, Local
from core.thread import thread
from .models import selected

async def main () -> None:

    models = await selected()
    engine = Llm()
    results: dict[str, object] = {}

    for role, spec in models.items():
        provider = Local(spec, name=role)
        engine.register(provider)
        started = date.tick()
        await engine.start(role)
        cold = date.elapsed(started)
        again = date.tick()
        await engine.start(role)
        warm = date.elapsed(again)
        prompt = engine.use(role)

        try:
            if role == "generation":
                response = await prompt.max_tokens(40).temperature(0).ask(
                    "Reply with exactly the word READY and nothing else.",
                )
                if response.text.strip() != "READY":
                    raise ValueError(response.dump())
                output: object = response.dump()
            elif role == "embedding":
                response_vectors = await prompt.embed(
                    ["How do I reset my password?", "كيف أعيد تعيين كلمة المرور؟"],
                    EmbeddingOptions(query=True, instruction="Retrieve relevant support instructions."),
                )
                output = {
                    "count": len(response_vectors.vectors), "dimension": len(response_vectors.vectors[0]),
                    "first_values": response_vectors.vectors[0][:4],
                }
            else:
                ranking = await prompt.rank(
                    "How do I reset my password?",
                    ["Open account security and choose reset password.", "The cafe serves fresh bread."],
                )
                output = [{"index": item.index, "score": item.score} for item in ranking]

            results[role] = {"start_ms": cold, "reuse_ms": warm, "output": output}
            await fs.write_json("evidence/local-smoke.json", results)
        finally:
            await provider.close()

    await engine.close()

if __name__ == "__main__":

    thread.run(main())
