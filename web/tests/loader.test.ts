import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { createTools, guard } from "@/lib/std/tooling";

const specTools = ( root: string ) =>
    createTools({
        root,
        variable: "SPEC",
        locales: ["en"],
        catalogue: { operations: [], features: [] } as never,
        validate: (( input: unknown ) => input) as never,
        assets: [],
        architecture: { foundation: /^engine\//, html: true, owners: {}, layers: [] },
    });

describe("spec folders", () => {

    test("specs are named in lowercase words, the demo first behind its leading underscore", () => {

        const root = mkdtempSync(resolve(tmpdir(), "engine-specs-"));

        for ( const spec of ["shop", "_demo"] ) mkdirSync(resolve(root, "specs", spec, "config"), { recursive: true });

        const tools = specTools(root);

        expect(tools.loader.installedSpecs()).toEqual(["_demo", "shop"]);
        expect(tools.loader.selectSpec()).toBe("_demo");
        expect(tools.loader.selectSpec("shop")).toBe("shop");
        expect(() => tools.loader.selectSpec("__demo")).toThrow("leading underscore");
        expect(() => tools.loader.selectSpec("Shop")).toThrow("leading underscore");

    });
    test("a (group) folder at any depth is transparent: the first plain folder is the spec, named by itself or by its path", () => {

        const root = mkdtempSync(resolve(tmpdir(), "engine-groups-"));
        const folders = [
            "shop/config",
            "_demo/schema",
            "(saasx)/client/config",
            "(saasx)/admin/schema",
            "(zainlak)/admin/config",
            "(saasx)/(v1)/(stage)/ops/config",
            "(saasx)/vendor/config",
            "(saasx)/vendor/(v1)/parts",
        ];

        for ( const folder of folders ) mkdirSync(resolve(root, "specs", folder), { recursive: true });

        const { loader } = specTools(root);

        expect(loader.installedSpecs()).toEqual([
            "_demo",
            "(saasx)/admin",
            "(zainlak)/admin",
            "(saasx)/client",
            "(saasx)/(v1)/(stage)/ops",
            "shop",
            "(saasx)/vendor",
        ]);
        expect(loader.selectSpec()).toBe("_demo");
        expect(loader.selectSpec("client")).toBe("(saasx)/client");
        expect(loader.selectSpec("ops")).toBe("(saasx)/(v1)/(stage)/ops");
        expect(loader.selectSpec("vendor")).toBe("(saasx)/vendor");
        expect(loader.selectSpec("(zainlak)/admin")).toBe("(zainlak)/admin");
        expect(() => loader.selectSpec("admin")).toThrow("(saasx)/admin, (zainlak)/admin");
        expect(() => loader.selectSpec("saasx/admin")).toThrow("(group) folders");
        expect(() => loader.selectSpec("(saasx)/nowhere")).toThrow("Unknown or missing spec");

    });
    test("a folder under specs is a spec or a (group), nothing else", () => {

        const plain = mkdtempSync(resolve(tmpdir(), "engine-plain-"));
        const cased = mkdtempSync(resolve(tmpdir(), "engine-cased-"));

        mkdirSync(resolve(plain, "specs", "saasx", "admin", "config"), { recursive: true });
        mkdirSync(resolve(cased, "specs", "(Saasx)", "admin", "config"), { recursive: true });

        expect(() => specTools(plain).loader.installedSpecs()).toThrow("is written (saasx)");
        expect(() => specTools(cased).loader.installedSpecs()).toThrow("neither a spec name nor a (group) folder");

    });
    test("a spec folder escaping the specs root is refused by the loader guard", () => {

        expect(() => guard("/part/specs", "/part/src/secret.ts", "Spec path escapes specs")).toThrow("escapes");
        expect(guard("/tmp", "/tmp/a.ts", "x")).toBe("/tmp/a.ts");

    });

});
