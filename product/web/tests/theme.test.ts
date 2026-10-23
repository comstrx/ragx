import { describe, expect, test } from "bun:test";
import { catalogueFacts } from "engine/spec";
import { validateSpec } from "../src/lib/spec/surface.ts";
import { bootScript, doorPage } from "../tools/boot.ts";
import { themeCss } from "../tools/theme.ts";

type Dataset = Record<string, string>;

function boot ( cookie: string, fallback = "system" ): string | undefined {

    const html = { dataset: {} as Dataset };

    new Function("document", bootScript("admin", fallback))({ cookie, documentElement: html });

    return html.dataset.theme;

}
function door ( cookie: string, languages: readonly string[] ): string {

    const page = doorPage({ identity: "admin", name: "A <b>&", routing: { locales: ["en", "ar"], defaultLocale: "en", localized: true } });
    const script = /<script>([\s\S]*?)<\/script>/.exec(page)?.[1] ?? "";
    const visited: string[] = [];

    new Function("document", "navigator", "location", script)({ cookie }, { languages }, { replace: ( to: string ) => visited.push(to) });

    return visited.join(",");

}
function compiled () {

    const messages = { en: {}, ar: {} };

    return validateSpec("site", { contents: { name: "Site", links: [] } }, { screens: [] }, messages, {}, catalogueFacts({})).config;

}

describe("theme boot", () => {

    test("the boot script reads the spec's own key and only trusts light or dark", () => {

        expect(boot("admin.theme=dark")).toBe("dark");
        expect(boot("other=1; admin.theme=light")).toBe("light");
        expect(boot("admin.theme=sepia")).toBeUndefined();
        expect(boot("xadmin.theme=dark")).toBeUndefined();
        expect(boot("admin.theme=system", "dark")).toBeUndefined();
        expect(boot("", "dark")).toBe("dark");

    });
    test("the export door honors the saved language, then the browser's, then the default, and escapes the name", () => {

        const page = doorPage({ identity: "admin", name: "A <b>&", routing: { locales: ["en", "ar"], defaultLocale: "en", localized: true } });

        expect(door("admin.language=ar", ["en"])).toBe("/ar");
        expect(door("admin.language=fr", ["ar-EG", "en"])).toBe("/ar");
        expect(door("", ["de"])).toBe("/en");
        expect(page).toContain("<title>A &lt;b&gt;&amp;</title>");
        expect(page).toContain('<meta name="robots" content="noindex">');
        expect(page).toContain('url=/en"');

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
        expect(css).toContain(':root[lang="en"] { --font-face:');
        expect(css).toContain(':root[lang="ar"] { --font-face:');
        expect(css).toContain("@font-face");

    });

});
