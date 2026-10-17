import type { Locale } from "@/lib/spec/languages";
import type { ScreenKind } from "@/lib/spec/surface";
import { absolute, ancestorsOf, crawlable, type Page, pageUrl, pictureOf, type Site } from "./site.ts";

export type Thing = Record<string, unknown>;
export type Graph = { "@context": "https://schema.org"; "@graph": Thing[] };

const kinds: Record<ScreenKind, string> = {
    page: "WebPage",
    about: "AboutPage",
    contact: "ContactPage",
    faq: "FAQPage",
    collection: "CollectionPage",
    article: "Article",
};

function compact ( thing: Thing ): Thing {

    return Object.fromEntries(Object.entries(thing).filter(( [, value] ) => value !== undefined && value !== null && value !== ""));

}
export function organization ( site: Site ): Thing {

    const { content } = site.config;
    const logo = content.logo ? absolute(site, content.logo) : undefined;
    const sameAs = content.socials.map(( social ) => social.href);
    const contact = content.email || content.phone
        ? compact({ "@type": "ContactPoint", contactType: "customer support", email: content.email, telephone: content.phone })
        : undefined;

    return compact({
        "@type": "Organization",
        "@id": absolute(site, "/#organization"),
        name: content.name,
        url: content.url,
        logo,
        ...(sameAs.length ? { sameAs } : {}),
        contactPoint: contact,
    });

}
export function website ( site: Site, locale: Locale ): Thing {

    return compact({
        "@type": "WebSite",
        "@id": absolute(site, "/#website"),
        url: pageUrl(site, locale, "/"),
        name: site.config.content.seo.title ?? site.config.content.name,
        description: site.config.content.seo.description ?? site.config.content.description,
        inLanguage: locale,
        publisher: { "@id": absolute(site, "/#organization") },
    });

}
export function breadcrumbs ( site: Site, page: Page, locale: Locale ): Thing | undefined {

    const trail = [...ancestorsOf(site, page.path), page];

    if ( trail.length < 2 ) return undefined;

    return {
        "@type": "BreadcrumbList",
        "@id": `${pageUrl(site, locale, page.path)}#breadcrumb`,
        itemListElement: trail.map(( step, index ) => ({
            "@type": "ListItem",
            position: index + 1,
            name: site.text(step.title, locale),
            item: pageUrl(site, locale, step.path),
        })),
    };

}
export function webPage ( site: Site, page: Page, locale: Locale ): Thing {

    const url = pageUrl(site, locale, page.path);
    const picture = pictureOf(site, page);
    const kind = page.kind ?? "page";
    const crumbs = breadcrumbs(site, page, locale);

    return compact({
        "@type": kinds[kind],
        "@id": url ? `${url}#${kind === "article" ? "article" : "webpage"}` : undefined,
        url,
        name: site.text(page.title, locale),
        ...(kind === "article" ? { headline: site.text(page.title, locale) } : {}),
        description: site.text(page.description, locale),
        inLanguage: locale,
        isPartOf: { "@id": absolute(site, "/#website") },
        ...(kind === "article" ? { author: { "@id": absolute(site, "/#organization") } } : {}),
        ...(kind === "article" ? { publisher: { "@id": absolute(site, "/#organization") } } : {}),
        primaryImageOfPage: picture ? { "@type": "ImageObject", url: picture } : undefined,
        breadcrumb: crumbs ? { "@id": crumbs["@id"] } : undefined,
    });

}
export function structuredData ( site: Site, page: Page, locale: Locale ): Graph | null {

    if ( !crawlable(site) || !page.indexed ) return null;

    const crumbs = breadcrumbs(site, page, locale);

    return {
        "@context": "https://schema.org",
        "@graph": [organization(site), website(site, locale), webPage(site, page, locale), ...(crumbs ? [crumbs] : [])],
    };

}
