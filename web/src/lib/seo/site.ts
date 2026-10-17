import type { Locale } from "@/lib/spec/languages";
import type { CompiledConfig, CompiledScreen } from "@/lib/spec/surface";
import { type MessageText, prefixed, type Routing } from "@/lib/std/translate";

export type Site = {
    config: CompiledConfig;
    screens: readonly CompiledScreen[];
    routing: Routing;
    text: ( value: MessageText, locale: Locale ) => string;
};
export type Page = Pick<CompiledScreen, "name" | "path" | "title" | "description" | "indexed"> &
    Partial<Pick<CompiledScreen, "image" | "kind" | "frequency" | "priority">>;

export function absolute ( site: Site, path: string ): string | undefined {

    return site.config.content.url ? `${site.config.content.url}${path}` : undefined;

}
export function pageUrl ( site: Site, locale: string, path: string ): string | undefined {

    return absolute(site, prefixed(locale, path));

}
export function languageLinks ( site: Site, path: string ): Record<string, string> {

    const links = site.routing.locales.flatMap(( locale ) => {

        const url = pageUrl(site, locale, path);

        return url ? [[locale, url] as const] : [];

    });
    const fallback = pageUrl(site, site.routing.defaultLocale, path);

    return Object.fromEntries(fallback ? [...links, ["x-default", fallback] as const] : links);

}
export function pictureOf ( site: Site, page: Page ): string | undefined {

    const chosen = page.image ?? site.config.content.seo.image ?? site.config.content.logo ?? undefined;

    if ( !chosen ) return undefined;

    return chosen.startsWith("/") ? (absolute(site, chosen) ?? chosen) : chosen;

}
export function crawlable ( site: Site ): boolean {

    return site.config.settings.seo && site.config.content.url !== null;

}
export function listedScreens ( site: Site ): CompiledScreen[] {

    return site.screens.filter(( screen ) => screen.indexed && !screen.path.includes(":"));

}
export function ancestorsOf ( site: Site, path: string ): CompiledScreen[] {

    const segments = path.split("/").filter(Boolean);
    const prefixes = segments.map(( _, index ) => `/${segments.slice(0, index).join("/")}`.replace(/\/$/, "") || "/");

    return prefixes.flatMap(( prefix ) => site.screens.filter(( screen ) => screen.path === prefix && !screen.path.includes(":")));

}
