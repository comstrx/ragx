import type { Metadata, MetadataRoute, Viewport } from "next";
import type { Locale } from "@/lib/spec/languages";
import { config, routing, screens, text } from "@/lib/spec/runtime";
import { pageMetadata as pageOf, siteMetadata as siteOf, siteViewport as viewportOf } from "./metadata.ts";
import { manifest as manifestOf, robots as robotsOf, sitemap as sitemapOf } from "./routes.ts";
import type { Page, Site } from "./site.ts";
import { type Graph, structuredData as graphOf } from "./structured.ts";

export type { Graph, Page, Site };

export const site: Site = { config, screens, routing, text };

export function pageMetadata ( page: Page, locale: Locale ): Metadata {

    return pageOf(site, page, locale);

}
export function structuredData ( page: Page, locale: Locale ): Graph | null {

    return graphOf(site, page, locale);

}
export function siteMetadata (): Metadata {

    return siteOf(site);

}
export function siteViewport (): Viewport {

    return viewportOf(site);

}
export function robots (): MetadataRoute.Robots {

    return robotsOf(site);

}
export function sitemap (): MetadataRoute.Sitemap {

    return sitemapOf(site);

}
export function manifest (): MetadataRoute.Manifest {

    return manifestOf(site);

}
