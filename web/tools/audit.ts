import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { brotliCompressSync } from "node:zlib";
import { report, task } from "@/lib/std/tooling";
import { directionOf, type Routing } from "@/lib/std/translate";
import { root } from "./core.ts";

export type Weight = { html: number; js: number; css: number; scripts: number };
export type Budget = { html: number; js: number; css: number };
export type Page = { html: string; locale: string; crawlable: boolean; routing: Routing };
export type Built = { identity: string; output: "export" | "standalone"; indexed: number; routing: Routing };

export const budgets: Record<Built["output"], Budget> = {
    export: { html: 4_000, js: 200_000, css: 12_000 },
    standalone: { html: 5_000, js: 200_000, css: 12_000 },
};

const scripts = /<script[^>]+src="([^"]+)"/g;
const sheets = /<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"|<link[^>]+href="([^"]+)"[^>]+rel="stylesheet"/g;

function squeezed ( bytes: Uint8Array ): number {

    return brotliCompressSync(bytes).byteLength;

}
function attribute ( html: string, name: string, of: RegExp ): string | undefined {

    return new RegExp(`<${of.source}[^>]*\\b${name}="([^"]*)"`).exec(html)?.[1];

}
export function weightOf ( html: string, read: ( url: string ) => Uint8Array | null ): Weight {

    const urls = [...html.matchAll(scripts)].map(( found ) => found[1] ?? "");
    const styles = [...html.matchAll(sheets)].map(( found ) => found[1] ?? found[2] ?? "");
    const sum = ( list: readonly string[] ): number => list.reduce(( total, url ) => total + squeezed(read(url) ?? new Uint8Array()), 0);

    return { html: squeezed(new TextEncoder().encode(html)), js: sum(urls), css: sum(styles), scripts: urls.length };

}
export function weightIssues ( where: string, weight: Weight, budget: Budget ): string[] {

    return (["html", "js", "css"] as const).flatMap(( part ) =>
        weight[part] > budget[part] ? [`${where}: ${part} weighs ${weight[part]} bytes brotli; the budget is ${budget[part]}.`] : [],
    );

}
export function pageIssues ({ html, locale, crawlable, routing }: Page): string[] {

    const where = `/${locale}`;
    const robots = attribute(html, "content", /meta[^>]*name="robots"/);
    const issues = [
        ...(attribute(html, "lang", /html/) === locale ? [] : [`${where}: <html lang> is not ${locale}.`]),
        ...(attribute(html, "dir", /html/) === directionOf(locale) ? [] : [`${where}: <html dir> is not ${directionOf(locale)}.`]),
        ...(/<title>[^<]+<\/title>/.test(html) ? [] : [`${where}: the page has no title.`]),
    ];

    if ( !crawlable ) return [...issues, ...(robots?.includes("noindex") ? [] : [`${where}: a site nobody may index must say noindex.`])];

    const graph = /<script type="application\/ld\+json">([^<]+)<\/script>/.exec(html)?.[1];
    const languages = [...routing.locales, "x-default"].filter(( language ) => !new RegExp(`hreflang="${language}"`, "i").test(html));
    const social = ["og:title", "og:url", "og:locale", "og:type"].filter(( name ) => !html.includes(`property="${name}"`));

    return [
        ...issues,
        ...(robots?.startsWith("index, follow") ? [] : [`${where}: an indexed page says index, follow.`]),
        ...(attribute(html, "href", /link[^>]*rel="canonical"/) ? [] : [`${where}: an indexed page names its canonical url.`]),
        ...(routing.localized && languages.length ? [`${where}: hreflang alternates are missing for ${languages.join(", ")}.`] : []),
        ...social.map(( name ) => `${where}: ${name} is missing.`),
        ...(html.includes('name="twitter:card"') ? [] : [`${where}: the twitter card is missing.`]),
        ...(graph && Array.isArray((JSON.parse(graph) as { "@graph"?: unknown })["@graph"]) ? [] : [`${where}: the JSON-LD graph is missing.`]),
    ];

}
export function crawlIssues ( robots: string, sitemap: string, crawlable: boolean, pages: number ): string[] {

    const entries = (sitemap.match(/<url>/g) ?? []).length;

    if ( !crawlable ) {

        return [
            ...(/Disallow: \/\s*$/m.test(robots) ? [] : ["robots.txt: a site nobody may index disallows everything."]),
            ...(entries === 0 ? [] : [`sitemap.xml: a site nobody may index lists no url, found ${entries}.`]),
        ];

    }

    return [
        ...(/^Sitemap: https?:\/\/\S+\/sitemap\.xml$/m.test(robots) ? [] : ["robots.txt: an indexed site links its sitemap."]),
        ...(/Disallow: \/\s*$/m.test(robots) ? ["robots.txt: an indexed site must not disallow everything."] : []),
        ...(entries === pages ? [] : [`sitemap.xml: expected ${pages} urls, found ${entries}.`]),
    ];

}
function file ( out: string, built: Built, name: string ): string {

    const served = name.endsWith(".html") ? name : `${name}.body`;
    const path = built.output === "export" ? resolve(out, name) : resolve(out, "server/app", served);

    if ( !existsSync(path) ) throw new Error(`The build has no ${name}; run bun run build first.`);

    return readFileSync(path, "utf8");

}
export function audit ( out: string, built: Built ): string[] {

    const crawlable = built.indexed > 0;
    const read = ( url: string ): Uint8Array | null => {

        const clean = url.replace(/\?.*$/, "");
        const path = [resolve(out, clean.replace(/^\/_next\//, "")), resolve(out, clean.replace(/^\//, ""))].find(existsSync);

        return path ? readFileSync(path) : null;

    };
    const pages = built.routing.locales.map(( locale ) => ({ locale, html: file(out, built, `${locale}.html`) }));
    const weights = pages.map(( page ) => ({ ...page, weight: weightOf(page.html, read) }));

    for ( const { locale, weight } of weights ) {

        report(`/${locale}: html ${weight.html} · js ${weight.js} (${weight.scripts} scripts) · css ${weight.css} bytes brotli`);

    }

    return [
        ...weights.flatMap(( page ) => weightIssues(`/${page.locale}`, page.weight, budgets[built.output])),
        ...pages.flatMap(( page ) => pageIssues({ html: page.html, locale: page.locale, crawlable, routing: built.routing })),
        ...crawlIssues(file(out, built, "robots.txt"), file(out, built, "sitemap.xml"), crawlable, built.indexed * built.routing.locales.length),
    ];

}

task(import.meta.url, () => {

    const built = JSON.parse(readFileSync(resolve(root, "node_modules/.cache/spec/production/meta.json"), "utf8")) as Built;
    const problems = audit(resolve(root, ".next/out"), built);

    if ( problems.length ) throw new Error(problems.join("\n"));

    report(`Audit: ${built.identity} (${built.output}) is within its budgets and says the right things to crawlers.`);

});
