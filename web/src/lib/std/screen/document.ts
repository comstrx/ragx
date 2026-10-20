export type Part = string | null | undefined;
export type Themed = { dataset: Record<string, string | undefined> };
export type Titled = { title: string };
export type Watched = Titled & { head: Node };

export const separator = " | ";

export function titleOf ( parts: readonly Part[] ): string {

    return parts.filter(( part ): part is string => typeof part === "string" && part.trim().length > 0).join(separator);

}
export function titled ( target: Titled, parts: readonly Part[] ): string {

    const title = titleOf(parts);

    if ( title && target.title !== title ) target.title = title;

    return title;

}
export function held ( target: Watched, parts: readonly Part[] ): () => void {

    const title = titled(target, parts);
    const keep = new MutationObserver(() => {

        if ( title && target.title !== title ) target.title = title;

    });

    keep.observe(target.head, { childList: true, subtree: true, characterData: true });

    return () => keep.disconnect();

}
export function isCurrent ( pathname: string, href: string, home: string ): boolean {

    const path = pathname.replace(/\/+$/, "") || "/";

    if ( path === href ) return true;

    return href !== home && path.startsWith(`${href}/`);

}
export function themeOn ( root: Themed, theme: string ): void {

    if ( theme === "light" || theme === "dark" ) root.dataset.theme = theme;
    else delete root.dataset.theme;

}
