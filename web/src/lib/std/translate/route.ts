import { negotiate } from "./locale.ts";

export type Routing = { locales: readonly string[]; defaultLocale: string; localized: boolean };
export type Located = { locale: string; path: string; explicit: boolean };
export type Visit = { path: string; language?: string | undefined; accept?: string | null | undefined };
export type Reserved = { roots: readonly string[]; files: readonly string[] };
export type Way =
    | { kind: "pass"; locale: string }
    | { kind: "rewrite"; locale: string; path: string }
    | { kind: "redirect"; path: string; status: 307 | 308 };

export function splitLocale ( pathname: string, routing: Pick<Routing, "locales" | "defaultLocale"> ): Located {

    const [, first = "", ...rest] = pathname.split("/");

    if ( !routing.locales.includes(first) ) return { locale: routing.defaultLocale, path: pathname || "/", explicit: false };

    return { locale: first, path: `/${rest.join("/")}`, explicit: true };

}
export function prefixed ( locale: string, path: string ): string {

    return path === "/" ? `/${locale}` : `/${locale}${path}`;

}
export function hrefOf ( locale: string, path: string, routing: Routing ): string {

    return routing.localized ? prefixed(locale, path) : path;

}
export function switched ( pathname: string, locale: string, routing: Routing ): string | null {

    return routing.localized ? prefixed(locale, splitLocale(pathname, routing).path) : null;

}
export function chosenLocale ( routing: Routing, language?: string | undefined, accept?: string | null | undefined ): string {

    if ( language && routing.locales.includes(language) ) return language;

    return negotiate(accept, routing.locales) ?? routing.defaultLocale;

}
export function routable ( path: string, reserved: Reserved ): boolean {

    const [, first = ""] = path.split("/");

    return !reserved.roots.includes(first) && !reserved.files.includes(path);

}
export function routeOf ( visit: Visit, routing: Routing ): Way {

    const located = splitLocale(visit.path, routing);

    if ( located.explicit && routing.localized ) return { kind: "pass", locale: located.locale };
    if ( located.explicit ) return { kind: "redirect", path: located.path, status: 308 };

    const locale = chosenLocale(routing, visit.language, visit.accept);
    const path = prefixed(locale, located.path);

    return routing.localized ? { kind: "redirect", path, status: 307 } : { kind: "rewrite", locale, path };

}
