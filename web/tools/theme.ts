import type { CompiledConfig } from "@/lib/spec/surface";
import { base64 } from "@/lib/std/base";
import { dataUri } from "@/lib/std/file";
import { publishedUrls } from "@/lib/std/tooling";
import {
    cssVariables,
    defineTokens,
    fontFace,
    fontFaces,
    fontOf,
    fontStack,
    languages,
    fonts as worldFonts,
} from "@/lib/std/world";

type Face = { file: string; weight: string };

const bare = { space: {}, radius: {}, type: {} };

function face ( locale: string, font: Face, assets: ReadonlyMap<string, Uint8Array> ): string {

    if ( !assets.has(`fonts/${font.file}`) ) throw new Error(`Missing selected font: ${font.file}`);

    return fontFace({ family: `Web-${locale}`, src: publishedUrls(`/fonts/${font.file}`, assets), weight: font.weight });

}
function family ( locale: string, locales: string[] ): string {

    const stack = [locale, ...locales.filter(( other ) => other !== locale)].map(( name ) => `Web-${name}`);

    return `:root[lang="${locale}"] { --font-face: ${fontStack(stack)}; }`;

}
function worldFamily ( locale: string ): string {

    const first = fontOf(languages.get(locale)?.script ?? "").family;
    const stack = [first, ...worldFonts.map(( font ) => font.family).filter(( family ) => family !== first)];

    return `:root[lang="${locale}"] { --font-face: ${fontStack(stack)}; }`;

}
export function themeCss ( config: CompiledConfig, assets: ReadonlyMap<string, Uint8Array>, icons: Uint8Array ): string {

    const fonts = Object.entries(config.settings.fonts);
    const locales = fonts.map(( [locale] ) => locale);
    const tokens = defineTokens({ colors: config.theme.colors, ...bare });
    const glyphs = fontFace({ family: "icons", src: dataUri("font/woff2", base64(icons)), weight: 400, display: "block" });

    return [
        glyphs,
        ...(fonts.length ? fonts.flatMap(( [locale, faces] ) => faces.map(( font ) => face(locale, font, assets))) : fontFaces()),
        cssVariables(tokens, "light", ":root"),
        cssVariables(tokens, "dark", '[data-theme="dark"]'),
        `@media (prefers-color-scheme: dark) {\n${cssVariables(tokens, "dark", ':root:not([data-theme="light"])')}\n}`,
        ...(fonts.length ? locales.map(( locale ) => family(locale, locales)) : config.settings.locale.enabled.map(worldFamily)),
        "",
    ].join("\n");

}
