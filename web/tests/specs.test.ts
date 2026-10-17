import { describe, expect, test } from "bun:test";
import { get, many, post } from "@/lib/std/api";
import { type Catalogue, catalogueFacts, type Features, type Manifest } from "@/lib/std/spec";
import { z } from "@/lib/std/validate";
import { block, feature, screen, site, surface, type Tree, validateSpec, write } from "../src/lib/spec/surface.ts";

const { read, t } = surface.define;

const state = { loading: "Loading", failed: "Failed", offline: "Offline", cached: "Saved", empty: "Empty", retry: "Retry", missing: "Missing" };
const messages = { en: { nav: { home: "Home" }, state }, ar: { nav: { home: "الرئيسية" }, state } };
const item = z.object({ id: z.number(), title: z.string(), image: z.string().nullish() });
const catalogue: Catalogue = catalogueFacts({
    products: {
        list: get("/products", { limit: z.number().optional() }, many(item)),
        view: get("/products/{productId}", { productId: z.number() }, item),
        save: post("/products", { title: z.string() }, item),
    },
});
const heroManifest: Manifest = {
    owner: "client",
    options: { prominent: false, loading: "", failed: "", offline: "", cached: "" },
    ports: { brand: { kind: "one", fields: ["name"], required: false } },
    access: [],
    signals: [],
};
const features: Features = {
    cards: {
        owner: "client",
        options: { columns: 3, title: "", loading: "", failed: "", offline: "", cached: "", empty: "" },
        ports: { items: { kind: "list", fields: ["title"] } },
        access: [],
        signals: [],
    },
    editor: { owner: "client", options: { failed: "", errors: {} }, ports: { save: { kind: "write" } }, access: [], signals: [] },
    hero: heroManifest,
};
const backend = { urls: { production: "https://api.example.test", local: null, browser: null }, options: {} as Record<string, never> };
const contents = { name: "Site", links: [] };
const home = ( ...children: Tree ) => screen({
    contents: { name: "home", path: "/", title: t("nav.home"), description: t("nav.home") },
    blocks: [block({}, children)],
});
const hero = () => feature("hero", { heading: true });

function compile ( schema: unknown, contracts: unknown = backend, settings: unknown = {} ) {

    return validateSpec("site", { contents, contracts, settings }, schema, messages, features, catalogue);

}
function build ( site: unknown, settings: unknown, schema: unknown ) {

    return validateSpec("site", { contents: site, contracts: backend, settings }, schema, messages, features, catalogue);

}
function issues ( schema: unknown, contracts: unknown = backend, settings: unknown = {} ): string {

    try { compile(schema, contracts, settings); }
    catch ( error ) { return error instanceof Error ? error.message : String(error); }

    return "";

}
describe("ports", () => {

    test("a read binds a list port and records the operation", () => {

        const cards = feature("cards", { ports: { items: read("products.list", { limit: 8 }) } });
        const { schema } = compile({ screens: [home(hero(), cards)] });
        const [first] = schema.screens;

        expect(schema.operations).toEqual(["products.list"]);
        expect(first?.blocks[0]?.features[1]?.ports.items).toEqual({
            kind: "read",
            feature: "products",
            operation: "list",
            input: { limit: 8 },
            many: true,
        });

    });
    test("a list port refuses a one-row read", () => {

        const cards = feature("cards", { ports: { items: read("products.view", { productId: 1 }) } });

        expect(issues({ screens: [home(hero(), cards)] })).toContain("answers one row");

    });
    test("a required port must be bound", () => {

        expect(issues({ screens: [home(hero(), feature("cards"))] })).toContain("needs its items port bound");

    });
    test("a site binding checks the document fields", () => {

        expect(issues({ screens: [home(feature("hero", { heading: true, ports: { brand: site("links") } }))] })).toContain("wants one row");
        expect(issues({ screens: [home(feature("hero", { heading: true, ports: { brand: site() } }))] })).toBe("");

    });
    test("a spec without a backend cannot read", () => {

        const cards = feature("cards", { ports: { items: read("products.list") } });

        expect(issues({ screens: [home(hero(), cards)] }, null)).toContain("declares none");

    });
    test("a write belongs to a client-owned feature and a GET cannot be written", () => {

        const editor = ( operation: string ) =>
            feature("editor", { options: { failed: "x", errors: t("nav") }, ports: { save: write(operation) } });

        expect(issues({ screens: [home(hero(), editor("products.list"))] })).toContain("is a read, not a write");
        expect(issues({ screens: [home(hero(), editor("products.save"))] })).toBe("");

    });
    test("unknown inputs and unbound path parameters are refused", () => {

        const bad = { screens: [home(hero(), feature("cards", { ports: { items: read("products.list", { page: 2 }) } }))] };

        expect(issues(bad)).toContain("unknown input page");

    });

});
describe("screens", () => {

    test("options merge over the settings and exactly one heading is required", () => {

        expect(issues({ screens: [home(feature("hero"))] })).toContain("exactly one feature owns the screen heading");

    });
    test("a server-owned feature needs a server-rendered screen; the client default refuses it, render: server welcomes it", () => {

        const served: Features = { ...features, hero: { ...heroManifest, owner: "server" } };
        const schema = { screens: [home(hero())] };
        const server = { screen: { render: "server" } };

        const site = { ...contents, url: "https://site.test" };
        const client = validateSpec("site", { contents: site, contracts: backend, settings: server }, schema, messages, served, catalogue);

        expect(() => validateSpec("site", { contents, contracts: backend }, schema, messages, served, catalogue)).toThrow("client-owned");
        expect(client.schema.screens[0]?.client).toBe(false);

    });
    test("indexing is behavior: a public server-rendered screen is indexed, needs the site url, and robots rules need one", () => {

        const first = home(hero());
        const schema = { screens: [first] };
        const site = { ...contents, url: "https://site.test" };
        const served = { screen: { render: "server" } };
        const robots = { ...contents, seo: { robots: { allow: ["/"] } } };
        const listed = { ...site, seo: { sitemap: ["*"] } };
        const insisted = { screens: [{ ...first, contents: { ...first.contents, index: true } }] };

        expect(issues(schema, backend, served)).toContain("needs contents.url");
        expect(build(site, served, schema).schema.screens[0]?.indexed).toBe(true);
        expect(build(site, served, schema).schema.indexed).toBe(1);
        expect(compile(schema).schema.screens[0]?.indexed).toBe(false);
        expect(compile(schema).schema.indexed).toBe(0);
        expect(issues(insisted)).toContain('index: true needs render: "server"');
        expect(() => build(robots, {}, schema)).toThrow("no screen is indexable");
        expect(() => build(listed, served, schema)).toThrow("derived from the screens");

    });
    test("a gated or unlisted screen is never indexed, and an export cannot server-render a backend read", () => {

        const site = { ...contents, url: "https://site.test" };
        const settings = ( output: string ) => ({ output, screen: { render: "server" } });
        const cards = feature("cards", { ports: { items: read("products.list") } });
        const page = { title: t("nav.home"), description: t("nav.home") };
        const gated = { contents: { name: "account", path: "/account", ...page }, access: "user", redirect: "/", blocks: [] };
        const unlisted = { contents: { name: "draft", path: "/draft", ...page, index: false }, blocks: [] };
        const compiled = build(site, settings("standalone"), { screens: [home(hero(), cards), gated, unlisted] });

        expect(compiled.schema.screens.map(( screen ) => screen.indexed)).toEqual([true, false, false]);
        expect(() => build(site, settings("export"), { screens: [home(hero(), cards)] })).toThrow("cannot server-render backend reads");

    });
    test("a gated screen names its redirect and compiles client", () => {

        const gated = {
            contents: { name: "account", path: "/account", title: t("nav.home"), description: t("nav.home") },
            access: "user",
            redirect: "/",
            blocks: [],
        };
        const { schema } = compile({ screens: [home(hero()), gated] });

        expect(schema.screens[1]?.client).toBe(true);
        expect(issues({ screens: [home(hero()), { ...gated, redirect: undefined }] })).toContain("names its redirect");

    });
    test("feature options are checked against the manifest", () => {

        const prominent = feature("hero", { heading: true, options: { prominent: "yes" } });
        const artful = feature("hero", { heading: true, options: { art: true } });

        expect(issues({ screens: [home(prominent)] })).toContain("takes boolean, not string");
        expect(issues({ screens: [home(artful)] })).toContain("has no option art");

    });
    test("every message must exist in every enabled language", () => {

        const page = { name: "home", path: "/", title: t("nav.missing"), description: t("nav.home") };
        const schema = { screens: [{ contents: page, blocks: [] }] };

        expect(issues(schema)).toContain('missing en message "nav.missing"');

    });
    test("a parameterised path cannot be exported, so the compiler refuses it", () => {

        const detail = { name: "item", path: "/items/:id", title: t("nav.home"), description: t("nav.home") };
        const schema = { screens: [home(hero()), { contents: detail, blocks: [] }] };

        expect(issues(schema)).toContain("parameterised paths");

    });
    test("the output mode is a setting: export by default, standalone on request, nothing else", () => {

        const schema = { screens: [home(hero())] };

        expect(compile(schema).config.settings.output).toBe("export");
        expect(compile(schema, backend, { output: "standalone" }).config.settings.output).toBe("standalone");
        expect(issues(schema, backend, { output: "static" })).toContain("output");

    });

});
