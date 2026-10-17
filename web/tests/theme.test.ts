import { describe, expect, test } from "bun:test";
import { catalogueFacts } from "@/lib/std/spec";
import { validateSpec } from "../src/lib/spec/surface.ts";
import { bootScript, themeCss } from "../tools/theme.ts";

type Dataset = Record<string, string>;

function boot ( stored: string | null, fallback = "system" ): string | undefined {

    const html = { dataset: {} as Dataset };
    const storage = { getItem: () => stored };

    new Function("localStorage", "document", bootScript("admin", fallback))(storage, { documentElement: html });

    return html.dataset.theme;

}
function compiled () {

    const messages = { en: {}, ar: {} };

    return validateSpec("site", { contents: { name: "Site", links: [] } }, { screens: [] }, messages, {}, catalogueFacts({})).config;

}

describe("theme boot", () => {

    test("the boot script reads the spec's own key and only trusts light or dark", () => {

        expect(bootScript("admin", "system")).toContain('"admin.theme"');
        expect(boot(JSON.stringify("dark"))).toBe("dark");
        expect(boot(JSON.stringify({ state: { theme: "light" } }))).toBe("light");
        expect(boot(JSON.stringify("sepia"))).toBeUndefined();
        expect(boot("{not json")).toBeUndefined();
        expect(boot(null, "dark")).toBe("dark");

    });

});
describe("theme css", () => {

    test("light tokens sit on :root, dark tokens on the attribute and the system preference, fonts per language", () => {

        const css = themeCss(compiled(), new Map(), new Uint8Array());

        expect(css).toContain(":root");
        expect(css).toContain("#0aa38a");
        expect(css).toContain('[data-theme="dark"]');
        expect(css).toContain("#2fd0b3");
        expect(css).toContain("@media (prefers-color-scheme: dark)");
        expect(css).toContain(':root:not([data-theme="light"])');
        expect(css).toContain(':root[lang="en"] { --font-sans:');
        expect(css).toContain(':root[lang="ar"] { --font-sans:');
        expect(css).toContain("@font-face");

    });

});
