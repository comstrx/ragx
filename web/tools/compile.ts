import { resolve } from "node:path";
import { browserConfig, connectionOrigins } from "@/lib/std/api";
import { unique } from "@/lib/std/array";
import { settingsResource } from "@/lib/std/spec";
import { featureEntry, featureFacts, iconFont, registryModule } from "@/lib/std/tooling";
import { emojis, iconAliases, iconNames } from "@/lib/std/world";
import { root, tools, writeFile } from "./core.ts";
import { securityHeaders } from "./security.ts";
import { bootScript, themeCss } from "./theme.ts";

type Reach = { path: string; features: readonly string[] };

function mountModule ( folder: string, names: readonly string[] ): string {

    const views = names.map(( name ) => `    ${JSON.stringify(name)}: dynamic(() => import(${featureEntry(root, folder, name)})),`);

    return `import dynamic from "next/dynamic";\n\nexport default {\n${views.join("\n")}\n};\n`;

}
function preloadModule ( folder: string, names: readonly string[], screens: readonly Reach[] ): string {

    const reach = screens.map(( screen ) => ({ path: screen.path, features: screen.features })).filter(( screen ) => screen.features.length);

    return `export const screens = ${JSON.stringify(reach)};\n\n${registryModule(root, folder, names)}`;

}

export const compileSpec = tools.build(import.meta.url, {
    brand: ( config ) => [config.content.logo, config.content.logo_dark, config.content.icon],
    engine: { flags: true, emoji: emojis.files, fonts: true },
    emit: async ({ spec, config, assets, folder }) => {

        const icons = await iconFont(iconNames, iconAliases, "woff2");
        const facts = await featureFacts(resolve(root, "src", "features"));
        const owned = ( owner: "client" | "server" ) => spec.schema.features.filter(( name ) => facts[name]?.owner === owner);
        const site = spec.config.content.url;
        const origins = connectionOrigins(spec.config.api);
        const media = unique([...origins, ...spec.config.settings.mediaOrigins]);
        writeFile("public/_generated/boot.js", bootScript(spec.identity, config.settings.theme.default));

        return {
            data: {
                settings: settingsResource(config.settings),
                build: { output: config.settings.output },
                browser: config.api ? { ...browserConfig(config.api, config.contract), realtime: config.realtime } : null,
            },
            registry: owned("server"),
            modules: {
                "mount.js": mountModule(folder, owned("client")),
                "preload.js": preloadModule(folder, owned("client"), spec.schema.screens),
                "theme.css": themeCss(config, assets, icons.bytes),
            },
            meta: {
                output: config.settings.output,
                indexed: spec.schema.indexed,
                connect: origins,
                secure: typeof site === "string" && site.startsWith("https://"),
                insecure: spec.config.insecure,
                media,
                security: securityHeaders({ connect: origins, media }),
            },
            note: `${owned("server").length} server-owned, ${owned("client").length} client-owned, ${spec.schema.indexed} indexed`,
        };

    },
});
