from typing import Any
from core.array import ranking
from core.date import date
from core.error import Code, Fault
from core.fs import Part, fs
from core.llm import Catalog, Harness, Llm, Local, RankingOptions
from core.rag import Document, Models, Policies, Rag, RagOptions
from core.thread import thread
from core.string import string

async def main (
    catalog: str = "src/usage/models.json", report: str = "evidence/local-rag.json", bilingual: bool = False,
) -> None:

    specs = await Catalog().load(catalog)
    engine = Llm()
    providers = {role: Local(spec, name=role) for role, spec in specs.items()}
    for provider in providers.values(): engine.register(provider)
    policy = Policies(
        generation=Harness(instructions=(
            ("Answer in a complete sentence in the language of the question. Preserve facts and their units. "
            "For a duration, always state the unit such as days or أيام; a bare number is incomplete. "
             "Preserve exactly what a deadline applies to. Do not add comparisons, exceptions or explanations "
             "absent from the sources. Use one factual sentence identifying the action, duration and starting event."),
        )),
    )
    rag = Rag(Models(
        engine.use("generation").temperature(0), engine.use("embedding"), engine.use("ranking"),
        engine.use("generation").temperature(0).max_tokens(160),
    ), policy, RagOptions(candidates=3, context_chars=3000))
    refund = "Customers can request a refund within 14 days of purchase."
    if bilingual: refund += "\nيمكن للعملاء طلب استرداد المبلغ خلال 14 يومًا من تاريخ الشراء."
    documents = [
        Document("refund", "refund-policy", (Part(refund),)),
        Document("security", "account-security", (
            Part("To reset a password, open Account Security and select Reset Password."),
        )),
        Document("hours", "opening-hours", (Part("Support is available Monday through Friday, 09:00 to 17:00 UTC."),)),
    ]
    started = date.tick()
    try:
        await engine.start("generation")
        generation_start_ms = date.elapsed(started)
        passages = await rag.ingest(documents, "workspace-demo")
        await providers["embedding"].close()
        await rag.save(".runtime/support-index.json")
        await rag.load(".runtime/support-index.json")
        questions = ["What is the refund period?", "ما مدة استرجاع المبلغ؟"]
        outputs: list[dict[str, Any]] = []
        for question in questions:
            arabic = string.search(question, "[\u0600-\u06ff]") is not None
            language = (
                "اكتب الإجابة باللغة العربية فقط، مع الحفاظ على المعنى والأرقام." if arabic else "Answer in English."
            )
            generation = engine.use("generation").temperature(0).max_tokens(160).instruct(language)
            result = await rag.ask(question, "workspace-demo", generation=generation)
            has_unit = any(unit in result.reply.text.lower() for unit in ("day", "يوم", "أيام", "ايام"))
            truth = frozenset(item.id for item in passages if item.source == "refund-policy")
            metrics = ranking.metrics([item.id for item in result.passages], truth, 3)
            outputs.append({
                "question": question, "answer": result.reply.text, "citations": result.citations,
                "recall_at_3": metrics.recall, "mrr": metrics.mrr, "ndcg_at_3": metrics.ndcg,
                "checks": {
                    "language_matches": (string.search(result.reply.text, "[\u0600-\u06ff]") is not None) == arabic,
                    "duration_and_unit": "14" in result.reply.text and has_unit,
                    "request_window": any(word in result.reply.text.lower() for word in (
                        "request a refund", "refund request", "طلب استرداد", "طلب استرجاع",
                        "طلب الاسترداد", "طلب الاسترجاع",
                    )),
                    "no_processing_claim": not any(word in result.reply.text.lower() for word in (
                        "processing", "معالجة", "صرف المبلغ",
                    )),
                    "citations_only_relevant": bool(result.citations) and set(result.citations).issubset(truth),
                },
            })
            if question == questions[0]:
                evaluation = await rag.evaluate(question, result)
                outputs[-1]["model_evaluation"] = {"score": evaluation.score, "reasoning": evaluation.reasoning}
                ranked = await engine.use("generation").temperature(0).rank(
                    question, [item.text for item in result.passages],
                    RankingOptions(method="generation", native_schema=True),
                )
                outputs[-1]["generative_ranking"] = [{"index": item.index, "score": item.score} for item in ranked]
            for provider in providers.values(): await provider.close()
        accepted = all(all(dict(item["checks"]).values()) for item in outputs)
        await fs.write_json(report, {
            "elapsed_ms": date.elapsed(started), "generation_start_ms": generation_start_ms,
            "generation_model": specs["generation"].name, "bilingual_sources": bilingual,
            "accepted": accepted, "cases": outputs,
        })
        if not accepted: raise Fault(Code.VALIDATION, reason="usage.semantic.acceptance")
    finally:
        await engine.close()

if __name__ == "__main__":

    thread.run(main())
