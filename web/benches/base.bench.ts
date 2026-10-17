import { deepMerge, pathGet } from "@/lib/std/base";
import { matchPattern } from "@/lib/std/parse";
import { bench, do_not_optimize, run } from "@/lib/std/tooling";

const document = { meta: { pagination: { page: 3 } } };

bench("matchPattern", () =>
    do_not_optimize(matchPattern("/items/:id/reviews/:reviewId", ["items", "7", "reviews", "9"])),
);
bench("pathGet", () => do_not_optimize(pathGet(document, "meta.pagination.page")));
bench("deepMerge", () => do_not_optimize(deepMerge(document, { meta: { pagination: { size: 20 } } })));

await run();
