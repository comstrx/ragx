import { describe, expect, test } from "bun:test";
import { get, many, post } from "@/lib/std/api";
import {
    catalogueFacts,
    compileBlock,
    contract,
    createWalk,
    data,
    type Features,
    feature,
    read,
    type SiteFeature,
    site,
    transportsOf,
    viewsOf,
    write,
} from "@/lib/std/spec";
import { viewFacts } from "@/lib/std/tooling";
import { z } from "@/lib/std/validate";

type Block = { gap: number };

const item = z.object({ id: z.number(), title: z.string() });
const catalogue = catalogueFacts({
    products: {
        list: get("/products", { limit: z.number().optional() }, many(item)),
        view: get("/products/{productId}", { productId: z.number() }, item),
        save: post("/products", { title: z.string() }, item),
    },
});
const features: Features = {
    cards: {
        owner: "server",
        options: { columns: 3 },
        ports: { items: { kind: "list", fields: ["title"] } },
        access: [],
        signals: [],
    },
    editor: { owner: "client", options: {}, ports: { save: { kind: "write" } }, access: [], signals: [] },
    hero: {
        owner: "server",
        options: {},
        ports: { brand: { kind: "one", fields: ["name"], required: false } },
        access: [],
        signals: [],
    },
};

function compile ( children: SiteFeature<Block>[], backend = true, params: string[] = [] ) {

    const walk = createWalk<Block>({
        params,
        client: false,
        session: false,
        backend,
        block: { gap: 4 },
        site: { name: "Site", links: [] },
        features,
        catalogue,
    });
    const block = compileBlock<Block>({ features: children }, walk, "home.blocks[0]");

    return { block, issues: walk.issues.join("\n"), operations: [...walk.operations] };

}
describe("ports", () => {

    test("a read binds a list port and records the operation", () => {

        const { block, issues, operations } = compile([
            feature("cards", { ports: { items: read("products.list", { limit: 8 }) } }),
        ]);

        expect(issues).toBe("");
        expect(operations).toEqual(["products.list"]);
        expect(block.features[0]?.ports.items).toEqual({
            kind: "read",
            feature: "products",
            operation: "list",
            input: { limit: 8 },
            many: true,
        });

    });
    test("a list port refuses a one-row read and a required port must be bound", () => {

        expect(
            compile([feature("cards", { ports: { items: read("products.view", { productId: 1 }) } })]).issues,
        ).toContain("answers one row");
        expect(compile([feature("cards")]).issues).toContain("needs its items port bound");

    });
    test("data and site bindings check their shape and fields", () => {

        expect(compile([feature("cards", { ports: { items: data([{ title: "a" }]) } })]).issues).toBe("");
        expect(compile([feature("cards", { ports: { items: data([{ name: "a" }]) } })]).issues).toContain(
            "lacks title",
        );
        expect(compile([feature("hero", { ports: { brand: site("links") } })]).issues).toContain("wants one row");
        expect(compile([feature("hero", { ports: { brand: site() } })]).issues).toBe("");

    });
    test("a spec without a backend cannot read, and a write needs a client owner", () => {

        expect(compile([feature("cards", { ports: { items: read("products.list") } })], false).issues).toContain(
            "declares none",
        );
        expect(compile([feature("editor", { ports: { save: write("products.list") } })]).issues).toContain(
            "is a read, not a write",
        );
        expect(compile([feature("editor", { ports: { save: write("products.save") } })]).issues).toBe("");

    });
    test("unknown inputs and unbound path parameters are refused", () => {

        expect(compile([feature("cards", { ports: { items: read("products.list", { page: 2 }) } })]).issues).toContain(
            "unknown input page",
        );
        expect(compile([feature("hero", { ports: { brand: read("products.view") } })]).issues).toContain(
            "{productId} is not bound",
        );

    });
    test("options are checked by kind and merged over the manifest", () => {

        expect(
            compile([feature("cards", { options: { columns: "3" }, ports: { items: data([{ title: "a" }]) } })]).issues,
        ).toContain("takes number, not string");
        expect(
            compile([feature("cards", { options: { rows: 1 }, ports: { items: data([{ title: "a" }]) } })]).issues,
        ).toContain("has no option rows");

    });

});
describe("feature contracts", () => {

    const list = get("/products", {}, many(item));
    const view = { owner: "client", options: { columns: 3 }, ports: { items: { kind: "list" } } } as const;
    const contracts = {
        site: contract({ transport: { read: list } }),
        shelf: contract({ transport: { list }, view }),
        banner: contract({ view: { owner: "server" } }),
    };

    test("a contract keeps its transport and its view apart, and the catalogue sees the transports only", () => {

        expect(Object.keys(transportsOf(contracts))).toEqual(["site", "shelf"]);
        expect(Object.keys(viewsOf(contracts))).toEqual(["shelf", "banner"]);
        expect(transportsOf(contracts).shelf.list).toBe(list);
        expect(viewsOf(contracts).shelf).toBe(view);
        expect(() => contract({})).toThrow("declares a transport, a view or both");

    });
    test("views become typed manifests, and a broken view names its contract file", () => {

        const facts = viewFacts(viewsOf(contracts));

        expect(Object.keys(facts)).toEqual(["banner", "shelf"]);
        expect(facts.banner).toEqual({ owner: "server", options: {}, ports: {}, access: [], signals: [] });
        expect(facts.shelf?.options).toEqual({ columns: 3 });
        expect(() => viewFacts({ odd: { owner: "edge" } })).toThrow("api/features/odd.ts view: owner");
        expect(() => viewFacts({ odd: { owner: "client", options: { empty: null } } })).toThrow(
            "api/features/odd.ts view options.empty: null defaults are not typed",
        );
        expect(() => viewFacts({ odd: { owner: "client", options: { at: new Date(0) } } })).toThrow("options are literal values only");

    });

});
