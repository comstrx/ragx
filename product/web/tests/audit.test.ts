import { describe, expect, test } from "bun:test";
import { budgets, crawlIssues, pageIssues, weightIssues, weightOf } from "../tools/audit.ts";

const routing = { locales: ["en", "ar"], defaultLocale: "en", localized: true };
const head = [
    '<link rel="canonical" href="https://site.test/en"/>',
    '<link rel="alternate" hrefLang="en" href="https://site.test/en"/>',
    '<link rel="alternate" hrefLang="ar" href="https://site.test/ar"/>',
    '<link rel="alternate" hrefLang="x-default" href="https://site.test/en"/>',
    '<meta name="robots" content="index, follow"/>',
    '<meta property="og:title" content="Home"/><meta property="og:url" content="https://site.test/en"/>',
    '<meta property="og:locale" content="en_US"/><meta property="og:type" content="website"/>',
    '<meta name="twitter:card" content="summary"/><title>Home | Site</title>',
].join("");
const graph = '<script type="application/ld+json">{"@context":"https://schema.org","@graph":[]}</script>';
const indexed = `<html lang="en" dir="ltr"><head>${head}</head><body>${graph}</body></html>`;
const of = ( html: string, locale = "en", crawlable = true ) => pageIssues({ html, locale, crawlable, routing });

describe("release audit", () => {

    test("an indexed page passes only with its language, canonical, alternates, social card and graph", () => {

        expect(of(indexed)).toEqual([]);
        expect(of(indexed.replace('lang="en"', 'lang="ar"'))).toEqual(["/en: <html lang> is not en."]);
        expect(of(indexed.replace(/<link rel="canonical"[^>]+>/, ""))).toEqual(["/en: an indexed page names its canonical url."]);
        expect(of(indexed.replace(/<link rel="alternate" hrefLang="ar"[^>]+>/, ""))).toEqual(["/en: hreflang alternates are missing for ar."]);
        expect(of(indexed.replace(graph, ""))).toEqual(["/en: the JSON-LD graph is missing."]);
        expect(of(indexed.replace(/<meta property="og:url"[^>]+>/, ""))).toEqual(["/en: og:url is missing."]);
        expect(of(indexed.replace("index, follow", "noindex"))).toEqual(["/en: an indexed page says index, follow."]);

    });
    test("a page nobody may index must say noindex and still carry its language and title", () => {

        const panel = '<html lang="ar" dir="rtl"><head><meta name="robots" content="noindex, nofollow"/><title>Admin</title></head></html>';

        expect(of(panel, "ar", false)).toEqual([]);
        expect(of(panel.replace("noindex, nofollow", "index, follow"), "ar", false)).toEqual(["/ar: a site nobody may index must say noindex."]);
        expect(of(panel.replace('dir="rtl"', 'dir="ltr"'), "ar", false)).toEqual(["/ar: <html dir> is not rtl."]);

    });
    test("robots and sitemap agree with the indexing: a listed site links its sitemap with every url, a closed one disallows all", () => {

        const open = "User-Agent: *\nAllow: /\n\nSitemap: https://site.test/sitemap.xml\n";
        const closed = "User-Agent: *\nDisallow: /\n";
        const listed = "<urlset><url><loc>a</loc></url><url><loc>b</loc></url></urlset>";

        expect(crawlIssues(open, listed, true, 2)).toEqual([]);
        expect(crawlIssues(open, listed, true, 4)).toEqual(["sitemap.xml: expected 4 urls, found 2."]);
        expect(crawlIssues(closed, listed, true, 2)).toEqual([
            "robots.txt: an indexed site links its sitemap.",
            "robots.txt: an indexed site must not disallow everything.",
        ]);
        expect(crawlIssues(closed, "<urlset></urlset>", false, 0)).toEqual([]);
        expect(crawlIssues(open, listed, false, 0)).toEqual([
            "robots.txt: a site nobody may index disallows everything.",
            "sitemap.xml: a site nobody may index lists no url, found 2.",
        ]);

    });
    test("weight counts every script and stylesheet the page loads, compressed, and refuses what exceeds the budget", () => {

        const encode = ( text: string ) => new TextEncoder().encode(text);
        const files: Record<string, Uint8Array> = { "/a.js": encode("x".repeat(5000)), "/b.css": encode("y".repeat(900)) };
        const page = '<html><head><link rel="stylesheet" href="/b.css"/></head><body><script src="/a.js"></script></body></html>';
        const weight = weightOf(page, ( url ) => files[url] ?? null);

        expect(weight.scripts).toBe(1);
        expect(weight.js).toBeGreaterThan(0);
        expect(weight.js).toBeLessThan(5000);
        expect(weight.css).toBeGreaterThan(0);
        expect(weightIssues("/en", { ...weight, js: budgets.export.js + 1 }, budgets.export)).toEqual([
            `/en: js weighs ${budgets.export.js + 1} bytes brotli; the budget is ${budgets.export.js}.`,
        ]);
        expect(weightIssues("/en", weight, budgets.export)).toEqual([]);

    });

});
