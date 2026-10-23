import { directionOf } from "engine/translate";
import type { MetadataRoute } from "next";
import { absolute, crawlable, languageLinks, listedScreens, pageUrl, type Site } from "./site.ts";

const mimes: Record<string, string> = {
    svg: "image/svg+xml",
    png: "image/png",
    webp: "image/webp",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    avif: "image/avif",
};

export function robots ( site: Site ): MetadataRoute.Robots {

    if ( !crawlable(site) ) return { rules: { userAgent: "*", disallow: "/" } };

    const { allow, disallow } = site.config.content.seo.robots;
    const sitemap = absolute(site, "/sitemap.xml");

    return {
        rules: { userAgent: "*", allow: allow.length ? allow : ["/"], ...(disallow.length ? { disallow } : {}) },
        ...(sitemap ? { sitemap } : {}),
    };

}
export function sitemap ( site: Site ): MetadataRoute.Sitemap {

    if ( !crawlable(site) ) return [];

    return listedScreens(site).flatMap(( screen ) =>
        site.routing.locales.flatMap(( locale ) => {

            const url = pageUrl(site, locale, screen.path);

            if ( !url ) return [];

            return [{
                url,
                ...(screen.frequency ? { changeFrequency: screen.frequency } : {}),
                ...(screen.priority !== undefined ? { priority: screen.priority } : {}),
                alternates: { languages: languageLinks(site, screen.path) },
            }];

        }),
    );

}
export function manifest ( site: Site ): MetadataRoute.Manifest {

    const { content, settings, theme } = site.config;
    const extension = content.icon?.split(".").pop() ?? "";

    return {
        name: content.name,
        short_name: content.name,
        ...(content.description ? { description: content.description } : {}),
        lang: settings.locale.default,
        dir: directionOf(settings.locale.default),
        start_url: "/",
        scope: "/",
        display: "standalone",
        background_color: theme.colors.light.body ?? "#ffffff",
        theme_color: theme.colors.light.primary ?? theme.colors.light.body ?? "#ffffff",
        icons: content.icon ? [{ src: content.icon, sizes: "any", type: mimes[extension] ?? "image/png" }] : [],
    };

}
