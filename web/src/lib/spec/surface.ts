import { core } from "@/api/core";
import { endpoints, entities, type Operation } from "@/api/features";
import {
    type Children,
    type CompiledBlock,
    type CompiledFeature,
    countShape,
    createSpecSurface,
    reads,
    specText,
    stepShape,
} from "@/lib/std/spec";
import { z } from "@/lib/std/validate";
import { iconNames } from "@/lib/std/world";
import english from "../../../messages/en.json" with { type: "json" };
import { supportedLocales } from "./languages.ts";
import { currency, themeDefaults } from "./theme.ts";

type Leaves<T, P extends string = ""> = T extends string
    ? P
    : { [K in keyof T & string]: Leaves<T[K], P extends "" ? K : `${P}.${K}`> }[keyof T & string];

export type MessageKey = Leaves<typeof english>;

const count = countShape(6);
const picture = z.string().regex(/^(?:\/images\/brand\/[a-zA-Z0-9/_-]+\.(?:png|webp|jpg|jpeg|svg|avif)|https:\/\/[^\s"'<>]+)$/);

export const screenKinds = ["page", "about", "contact", "faq", "collection", "article"] as const;
export const changeFrequencies = ["always", "hourly", "daily", "weekly", "monthly", "yearly", "never"] as const;

export const surface = createSpecSurface({
    kind: "web",
    locales: supportedLocales,
    entities,
    icons: iconNames,
    brand: {
        images: "/images/brand",
        imageFormats: ["png", "webp", "jpg", "jpeg", "svg", "avif"],
        fontFormats: ["woff2", "woff", "ttf", "otf"],
        fontWeight: /^[1-9]00(?: [1-9]00)?$/,
    },
    screenOptions: z.strictObject({
        render: z.enum(["server", "client"]),
        title: z.boolean(),
        nav: z.boolean(),
        footer: z.boolean(),
        sidebar: z.boolean(),
        loader: z.boolean(),
    }),
    blockOptions: z.strictObject({
        width: z.enum(["auto", "full", "half", "third", "two-thirds", "quarter", "narrow", "wide"]),
        height: z.enum(["auto", "screen"]),
        grid: z.union([count, z.partialRecord(z.enum(["base", "sm", "md", "lg", "xl"]), count)]),
        sizes: z.array(z.number().int().min(1).max(12)).max(12),
        gap: stepShape,
        padding: stepShape,
        align: z.enum(["start", "center", "end", "stretch"]),
        tone: z.enum(["default", "surface", "primary", "inverse"]),
        radius: z.enum(["none", "sm", "md", "lg", "xl"]),
        shadow: z.enum(["none", "sm", "md", "lg"]),
    }),
    shell: ["nav", "footer", "sidebar", "loader"],
    contents: {
        description: specText,
        image: picture.optional(),
        index: z.boolean().optional(),
        kind: z.enum(screenKinds).optional(),
        priority: z.number().min(0).max(1).optional(),
        frequency: z.enum(changeFrequencies).optional(),
    },
    settings: { output: z.enum(["export", "standalone"]), seo: z.boolean() },
    themeDefaults,
    settingsDefaults: {
        output: "export",
        seo: false,
        currency,
        screen: { render: "client", title: true, nav: true, footer: false, sidebar: true, loader: true },
        block: {
            width: "full",
            height: "auto",
            grid: 1,
            sizes: [],
            gap: 6,
            padding: 0,
            align: "stretch",
            tone: "default",
            radius: "none",
            shadow: "none",
        },
        shell: { nav: null, footer: null, sidebar: null, loader: null },
    },
    environment: process.env,
    contracts: { browser: true, options: {}, dropped: ["baseUrl", "browserBaseUrl", "development"] },
});

export const { configShape, configInputShape, schemaShape, screenOptions, blockOptions, shellShape, settingsShape, contentShape } = surface;
export const { defineConfig, defineSchema, screen, block, feature, write, data, site, param, query, signal, live, env } = surface.define;

export function t ( key: MessageKey ): ReturnType<typeof surface.define.t> {

    return surface.define.t(key);

}
export function read ( operation: Operation, ...rest: Parameters<typeof surface.define.read> extends [unknown, ...infer R] ? R : never ) {

    return surface.define.read(operation, ...rest);

}
export const validateSpec = surface.validator({
    reserved: new RegExp(`^/(?:_next|_generated|images|fonts|videos|audios|${supportedLocales.join("|")})(?:/|$)`),
    endpoints,
    core,
    walk: ( screen, options ) => ({ client: options.render === "client" || (screen.access ?? "any") !== "any", session: false }),
    configIssues: ({ content, settings }) => {

        const { robots, sitemap } = content.seo;

        return [
            ...(settings.seo && !content.url
                ? ["settings.seo needs contents.url: canonical links, the sitemap and the social cards are absolute."]
                : []),
            ...(!settings.seo && (robots.allow.length || robots.disallow.length)
                ? ["contents.seo.robots: this spec is not indexed (settings.seo is off); drop the rules or turn settings.seo on."]
                : []),
            ...(sitemap.length
                ? ["contents.seo.sitemap: the sitemap is derived from the screens; set index: false on a screen to leave it out."]
                : []),
        ];

    },
    screen: ( screen, options, config, compiled, issues ) => {

        const { name, path, index = true } = screen.contents;
        const access = screen.access ?? "any";
        const client = options.render === "client" || access !== "any";
        const indexed = config.settings.seo && access === "any" && index;
        const exported = config.settings.output === "export";

        if ( exported && compiled.walk.params.length )
            issues.push(`${path}: an export cannot build parameterised paths; set settings.output: "standalone".`);

        if ( indexed && client ) issues.push(`${name}: an indexed screen renders on the server; set render: "server" or index: false.`);

        if ( exported && !client && reads(compiled.blocks, []) )
            issues.push(`${name}: an export cannot server-render backend reads; set render: "client".`);

        return { client, indexed };

    },
});

export type SiteConfig = z.input<typeof configInputShape>;
export type CompiledConfig = z.output<typeof configShape>;
export type SiteSchemaInput = z.input<typeof schemaShape>;
export type Compiled = ReturnType<typeof validateSpec>;
export type CompiledSchema = Compiled["schema"];
export type CompiledScreen = CompiledSchema["screens"][number];
export type ScreenOptions = z.output<typeof screenOptions>;
export type BlockOptions = z.output<typeof blockOptions>;
export type Shell = z.output<typeof shellShape>;
export type ScreenKind = typeof screenKinds[number];
export type Tree = Children<BlockOptions>;
export type CompiledWebBlock = CompiledBlock<BlockOptions>;
export type CompiledWebFeature = CompiledFeature<BlockOptions>;
