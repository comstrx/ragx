import { bench, do_not_optimize, measured } from "@/lib/std/tooling";
import { routable, routeOf } from "@/lib/std/translate";
import { reserved } from "../src/lib/spec/routes.ts";
import { addressOf } from "../tools/serve.ts";

const localized = { locales: ["en", "ar", "fr", "de"], defaultLocale: "en", localized: true };
const plain = { ...localized, localized: false };
const asked = new Headers({ cookie: "theme=dark; admin.language=ar; other=1", "accept-language": "fr;q=0.9, ar;q=0.8" });
const built = { identity: "admin", output: "export" as const, routing: plain, reserved, language: "admin.language" };

bench("routeOf localized pass", () => do_not_optimize(routeOf({ path: "/ar/items/7" }, localized)));
bench("routeOf plain rewrite by cookie", () => do_not_optimize(routeOf({ path: "/items/7", language: "ar" }, plain)));
bench("routeOf plain rewrite by accept-language", () => do_not_optimize(routeOf({ path: "/items/7", accept: "fr;q=0.9, ar;q=0.8" }, plain)));
bench("routable asset", () => do_not_optimize(routable("/_next/static/chunks/a.js", reserved)));
bench("serve addressOf with cookies", () => do_not_optimize(addressOf("/settings", asked, built)));

await measured({
    "routeOf localized pass": 2,
    "routeOf plain rewrite by cookie": 2,
    "routeOf plain rewrite by accept-language": 6,
    "routable asset": 1,
    "serve addressOf with cookies": 12,
});
