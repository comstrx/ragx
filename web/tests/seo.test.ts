import { describe, expect, test } from "bun:test";
import { get } from "@/lib/std/api";
import { defineRuntime } from "@/lib/std/screen";
import { type Catalogue, catalogueFacts, type Features } from "@/lib/std/spec";
import { z } from "@/lib/std/validate";
import { pageMetadata, pageRobots, siteMetadata, siteViewport } from "../src/lib/seo/metadata.ts";
import { manifest, robots, sitemap } from "../src/lib/seo/routes.ts";
import type { Site } from "../src/lib/seo/site.ts";
import { breadcrumbs, structuredData } from "../src/lib/seo/structured.ts";
import type { CompiledScreen } from "../src/lib/spec/surface.ts";
import { block, feature, screen, surface, validateSpec } from "../src/lib/spec/surface.ts";

const { t } = surface.define;

const state = { loading: "Loading", failed: "Failed", offline: "Offline", cached: "Saved", empty: "Empty", retry: "Retry", missing: "Missing" };
const messages = {
    en: { nav: { home: "Home", about: "About", team: "Team" }, state },
    ar: { nav: { home: "الرئيسية", about: "من نحن", team: "الفريق" }, state },
};
const catalogue: Catalogue = catalogueFacts({
    hello: { read: get("/hello", {}, z.object({ message: z.string() })) },
});
const features: Features = {
    intro: {
        owner: "server",
        options: { title: "" },
        ports: { greeting: { kind: "one", fields: ["message"], required: false } },
        access: [],
        signals: [],
    },
};
const backend = { urls: { production: "https://api.site.test", local: null, browser: null }, options: {} as Record<string, never> };
const routing = { locales: ["en", "ar"], defaultLocale: "en" };
const aboutLinks = { en: "https://site.test/en/about", ar: "https://site.test/ar/about", "x-default": "https://site.test/en/about" };
const page = ( name: string, path: string, extra: Record<string, unknown> = {}, access?: string ) => screen({
    contents: { name, path, title: t(`nav.${name}`), description: t(`nav.${name}`), ...extra },
    ...(access ? { access, redirect: "/" } : {}),
    blocks: [block({}, [feature("intro", { heading: true, options: { title: t(`nav.${name}`) } })])],
} as never);
const screensOf = ( listed: boolean ) => [
    page("home", "/", { kind: "page", priority: 1, frequency: "weekly", ...(listed ? {} : { index: false }) }),
    page("about", "/about", { kind: "about", frequency: "monthly", ...(listed ? {} : { index: false }) }),
    page("team", "/about/team", { kind: "article", index: false }),
];

function siteOf ( settings: Record<string, unknown>, seo: Record<string, unknown> = {}, listed = true ): Site {

    const url = "https://site.test";
    const contents = { name: "Site", links: [], url, icon: "/images/brand/icon.svg", socials: [{ name: "x", href: "https://x.com/site" }], seo };
    const pages = screensOf(listed);
    const { config, schema } = validateSpec("site", { contents, contracts: backend, settings }, { screens: pages }, messages, features, catalogue);
    const runtime = defineRuntime<CompiledScreen, "en" | "ar">({ screens: schema.screens, shell: schema.shell, messages });

    return { config, screens: schema.screens, routing, text: runtime.text };

}

const indexed = siteOf({ output: "standalone", screen: { render: "server" } }, { title: "Site, the product", keywords: ["ai", "chat"] });
const silent = siteOf({ screen: { render: "server" } }, {}, false);
const [home, about, team] = indexed.screens as [CompiledScreen, CompiledScreen, CompiledScreen];

describe("page metadata", () => {

    test("an indexed page carries its canonical, every language link, the social card and open robots", () => {

        const meta = pageMetadata(indexed, about, "ar");

        expect(meta.title).toBe("من نحن");
        expect(meta.alternates?.canonical).toBe("https://site.test/ar/about");
        expect(meta.alternates?.languages).toEqual(aboutLinks);
        expect(meta.openGraph).toMatchObject({ type: "website", url: "https://site.test/ar/about", siteName: "Site", title: "من نحن" });
        expect(meta.openGraph).toMatchObject({ alternateLocale: ["en_US"] });
        expect(meta.twitter).toMatchObject({ card: "summary", title: "من نحن" });
        expect(meta.robots).toMatchObject({ index: true, follow: true, googleBot: { "max-image-preview": "large" } });

    });
    test("the home page takes the site title whole, an unlisted page is followed but not indexed, an article opens as one", () => {

        expect(pageMetadata(indexed, home, "en").title).toEqual({ absolute: "Site, the product" });
        expect(pageRobots(indexed, team)).toEqual({ index: false, follow: true });
        expect(pageMetadata(indexed, team, "en").openGraph).toMatchObject({ type: "article" });

    });
    test("a spec without an indexable screen keeps its titles and descriptions but closes robots and skips links and cards", () => {

        const meta = pageMetadata(silent, silent.screens[1] as CompiledScreen, "en");

        expect(meta.title).toBe("About");
        expect(meta.description).toBe("About");
        expect(meta.robots).toEqual({ index: false, follow: false });
        expect(meta.alternates).toBeUndefined();
        expect(meta.openGraph).toBeUndefined();

    });
    test("the site metadata templates the title, bases urls on the site, lists keywords and verification only when indexed", () => {

        const open = siteMetadata(indexed);
        const closed = siteMetadata(silent);

        expect(open.title).toEqual({ default: "Site, the product", template: "%s · Site" });
        expect(String(open.metadataBase)).toBe("https://site.test/");
        expect(open.keywords).toEqual(["ai", "chat"]);
        expect(open.manifest).toBe("/manifest.webmanifest");
        expect(open.robots).toBeUndefined();
        expect(closed.robots).toEqual({ index: false, follow: false });
        expect(closed.keywords).toBeUndefined();
        expect(siteViewport(indexed).themeColor).toHaveLength(2);

    });

});
describe("structured data", () => {

    test("an indexed page ships an organization, the website, the typed page and its breadcrumb trail", () => {

        const graph = structuredData(indexed, about, "en");
        const types = graph?.["@graph"].map(( thing ) => thing["@type"]);

        expect(types).toEqual(["Organization", "WebSite", "AboutPage", "BreadcrumbList"]);
        expect(graph?.["@graph"][0]).toMatchObject({ name: "Site", url: "https://site.test", sameAs: ["https://x.com/site"] });
        expect(graph?.["@graph"][2]).toMatchObject({ url: "https://site.test/en/about", inLanguage: "en" });
        expect(graph?.["@graph"][2]).toMatchObject({ isPartOf: { "@id": "https://site.test/#website" } });
        expect(breadcrumbs(indexed, about, "en")?.itemListElement).toEqual([
            { "@type": "ListItem", position: 1, name: "Home", item: "https://site.test/en" },
            { "@type": "ListItem", position: 2, name: "About", item: "https://site.test/en/about" },
        ]);

    });
    test("home has no breadcrumb, a nested page walks every ancestor, nothing ships without an indexable screen or for an unlisted page", () => {

        expect(structuredData(indexed, home, "en")?.["@graph"].map(( thing ) => thing["@type"])).toEqual(["Organization", "WebSite", "WebPage"]);
        expect(breadcrumbs(indexed, team, "en")?.itemListElement).toHaveLength(3);
        expect(structuredData(indexed, team, "en")).toBeNull();
        expect(structuredData(silent, silent.screens[0] as CompiledScreen, "en")).toBeNull();

    });

});
describe("robots, sitemap and manifest", () => {

    test("robots open the site and point at the sitemap when indexed, and close everything otherwise", () => {

        expect(robots(indexed)).toEqual({ rules: { userAgent: "*", allow: ["/"] }, sitemap: "https://site.test/sitemap.xml" });
        expect(robots(siteOf({ screen: { render: "server" } }, { robots: { allow: ["/", "/about"], disallow: ["/private"] } })).rules)
            .toEqual({ userAgent: "*", allow: ["/", "/about"], disallow: ["/private"] });
        expect(robots(silent)).toEqual({ rules: { userAgent: "*", disallow: "/" } });

    });
    test("the sitemap lists every indexed static screen in every language with its alternates, frequency and priority", () => {

        const entries = sitemap(indexed);

        expect(entries.map(( entry ) => entry.url)).toEqual([
            "https://site.test/en",
            "https://site.test/ar",
            "https://site.test/en/about",
            "https://site.test/ar/about",
        ]);
        expect(entries[0]).toMatchObject({ changeFrequency: "weekly", priority: 1 });
        expect(entries[2]?.alternates?.languages).toEqual(aboutLinks);
        expect(sitemap(silent)).toEqual([]);

    });
    test("the manifest names the app, its language and direction, the theme colors and the brand icon", () => {

        expect(manifest(indexed)).toMatchObject({
            name: "Site",
            lang: "en",
            dir: "ltr",
            start_url: "/",
            display: "standalone",
            theme_color: "#0aa38a",
            icons: [{ src: "/images/brand/icon.svg", sizes: "any", type: "image/svg+xml" }],
        });

    });

});
