import { preferenceNames } from "engine/cookie";
import { directionOf, type Routing } from "engine/translate";

export type Door = { identity: string; name: string; routing: Routing };

const special = /[.*+?^${}()|[\]\\]/g;
const entities: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

function escaped ( text: string ): string {

    return text.replace(/[&<>"']/g, ( found ) => entities[found] ?? found);

}
function cookieOf ( name: string ): string {

    const pattern = `/(?:^|;\\s*)${name.replace(special, "\\$&")}=([^;]*)/`;

    return `var found = document.cookie.match(${pattern}); var saved = found ? decodeURIComponent(found[1]) : null;`;

}
export function bootScript ( identity: string, fallback: string ): string {

    return [
        "(function () {",
        `    ${cookieOf(preferenceNames(identity).theme)}`,
        `    var theme = ["light", "dark", "system"].indexOf(saved) === -1 ? ${JSON.stringify(fallback)} : saved;`,
        `    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;`,
        "})();",
        "",
    ].join("\n");

}
export function doorPage ({ identity, name, routing }: Door): string {

    const fallback = routing.defaultLocale;
    const locales = JSON.stringify(routing.locales);
    const choose = [
        "(function () {",
        `    var locales = ${locales};`,
        `    ${cookieOf(preferenceNames(identity).language)}`,
        "    var chosen = locales.indexOf(saved) === -1 ? null : saved;",
        "    var asked = navigator.languages || [];",
        "    for (var index = 0; index < asked.length && !chosen; index += 1) {",
        '        var base = String(asked[index]).split("-")[0].toLowerCase();',
        "        if (locales.indexOf(base) !== -1) chosen = base;",
        "    }",
        `    location.replace("/" + (chosen || ${JSON.stringify(fallback)}));`,
        "})();",
    ].join("\n");

    return [
        "<!doctype html>",
        `<html lang="${fallback}" dir="${directionOf(fallback)}">`,
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="robots" content="noindex">',
        `<title>${escaped(name)}</title>`,
        `<script>\n${choose}\n</script>`,
        `<noscript><meta http-equiv="refresh" content="0; url=/${fallback}"></noscript>`,
        "</head>",
        `<body><a href="/${fallback}">${escaped(name)}</a></body>`,
        "</html>",
        "",
    ].join("\n");

}
