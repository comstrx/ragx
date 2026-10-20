import { interpolate } from "@/lib/std/parse";
import { bench, do_not_optimize, measured  } from "@/lib/std/tooling";
import { formatDate, formatMoney, negotiate, plural, translator } from "@/lib/std/translate";

const t = translator({ cart: { items: "{count} items for {total}" } });
const at = new Date(Date.UTC(2026, 9, 13));

bench("negotiate", () => do_not_optimize(negotiate("de, ar;q=0.8, en;q=0.9", ["en", "ar"])));
bench("translator.interpolate", () => do_not_optimize(t("cart.items", { count: 3, total: "$10" })));
bench("interpolate dotted", () => do_not_optimize(interpolate("{a.b} and {c}", { a: { b: 1 }, c: 2 })));
bench("formatMoney", () => do_not_optimize(formatMoney("ar", 1234.5, "USD")));
bench("formatDate", () => do_not_optimize(formatDate("en", at, "day", "UTC")));
bench("plural", () => do_not_optimize(plural("ar", 3, { other: "{n} items", few: "{n} items" })));

await measured({
    "negotiate": 15,
    "translator.interpolate": 7,
    "interpolate dotted": 4,
    "formatMoney": 65,
    "formatDate": 30,
    "plural": 7,
});
