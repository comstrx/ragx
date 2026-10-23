import { separator } from "engine/screen";
import type { Metadata, Viewport } from "next";
import { type Locale, languages } from "@/lib/spec/languages";
import { crawlable, languageLinks, type Page, pageUrl, pictureOf, type Site } from "./site.ts";

type Robots = NonNullable<Metadata["robots"]>;

const known = ["google", "yandex", "yahoo", "me"] as const;
const previews = { "max-image-preview": "large", "max-snippet": -1, "max-video-preview": -1 } as const;

function verificationOf ( given: Readonly<Record<string, string>> ): Metadata["verification"] {

    const entries = Object.entries(given).filter(( [, value] ) => value.length > 0);

    if ( !entries.length ) return undefined;

    const named = Object.fromEntries(entries.filter(( [key] ) => (known as readonly string[]).includes(key)));
    const other = Object.fromEntries(entries.filter(( [key] ) => !(known as readonly string[]).includes(key)));

    return { ...named, ...(Object.keys(other).length ? { other } : {}) };

}
export function pageRobots ( site: Site, page: Pick<Page, "indexed"> ): Robots {

    if ( !crawlable(site) ) return { index: false, follow: false };
    if ( !page.indexed ) return { index: false, follow: true };

    return { index: true, follow: true, googleBot: { index: true, follow: true, ...previews } };

}
export function pageMetadata ( site: Site, page: Page, locale: Locale ): Metadata {

    const { name } = site.config.content;
    const title = site.text(page.title, locale);
    const description = site.text(page.description, locale);
    const picture = pictureOf(site, page);
    const url = pageUrl(site, locale, page.path);
    const others = site.routing.locales.filter(( other ) => other !== locale) as Locale[];
    const shared = {
        title: page.path === "/" ? { absolute: site.config.content.seo.title ?? name } : title,
        description,
        robots: pageRobots(site, page),
    };

    if ( !crawlable(site) ) return shared;

    return {
        ...shared,
        alternates: { canonical: url, languages: languageLinks(site, page.path) },
        openGraph: {
            type: page.kind === "article" ? "article" : "website",
            url,
            siteName: name,
            title,
            description,
            locale: languages[locale].openGraph,
            alternateLocale: others.map(( other ) => languages[other].openGraph),
            ...(picture ? { images: [{ url: picture, alt: title }] } : {}),
        },
        twitter: {
            card: picture ? "summary_large_image" : "summary",
            title,
            description,
            ...(site.config.content.seo.twitter ? { site: site.config.content.seo.twitter } : {}),
            ...(picture ? { images: [picture] } : {}),
        },
    };

}
export function siteMetadata ( site: Site ): Metadata {

    const { content } = site.config;
    const indexed = crawlable(site);

    return {
        ...(content.url ? { metadataBase: new URL(content.url) } : {}),
        title: { default: content.seo.title ?? content.name, template: `%s${separator}${content.name}` },
        description: content.seo.description ?? content.description ?? undefined,
        applicationName: content.name,
        ...(indexed && content.seo.keywords.length ? { keywords: content.seo.keywords } : {}),
        ...(content.icon ? { icons: { icon: content.icon } } : {}),
        manifest: "/manifest.webmanifest",
        ...(indexed ? { verification: verificationOf(content.seo.verification) } : { robots: { index: false, follow: false } }),
    };

}
export function siteViewport ( site: Site ): Viewport {

    const { light, dark } = site.config.theme.colors;

    return {
        width: "device-width",
        initialScale: 1,
        colorScheme: "light dark",
        themeColor: [
            { media: "(prefers-color-scheme: light)", color: light.body ?? "#ffffff" },
            { media: "(prefers-color-scheme: dark)", color: dark.body ?? "#000000" },
        ],
    };

}
