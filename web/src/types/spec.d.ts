declare module "@spec/theme.css";

declare module "@spec/config" {

    import type { CompiledConfig } from "@/lib/spec/surface";

    const config: CompiledConfig;

    export default config;

}
declare module "@spec/routing" {

    import type { Locale } from "@/lib/spec/languages";

    const routing: { locales: Locale[]; defaultLocale: Locale };

    export default routing;

}
declare module "@spec/settings" {

    import type { SettingsResource } from "@/lib/std/spec";

    const settings: SettingsResource;

    export default settings;

}
declare module "@spec/build" {

    const build: { output: "export" | "standalone" };

    export default build;

}
declare module "@spec/schema" {

    import type { CompiledSchema } from "@/lib/spec/surface";

    const schema: CompiledSchema;

    export default schema;

}
declare module "@spec/mount" {

    import type { ComponentType } from "react";
    import type { FeatureProps } from "@/lib/spec/feature";

    const views: Readonly<Record<string, ComponentType<FeatureProps>>>;

    export default views;

}
declare module "@spec/registry" {

    import type { ComponentType } from "react";
    import type { FeatureProps } from "@/lib/spec/feature";

    const loads: Readonly<Record<string, () => Promise<{ default: ComponentType<FeatureProps> }>>>;

    export default loads;

}
declare module "@spec/preload" {

    export const screens: readonly { path: string; features: readonly string[] }[];

    const loads: Readonly<Record<string, () => Promise<unknown>>>;

    export default loads;

}
declare module "@spec/messages" {

    import type { Messages } from "@/lib/std/translate";
    import type { Locale } from "@/lib/spec/languages";

    const dictionaries: Record<Locale, Messages>;

    export default dictionaries;

}
declare module "@spec/browser" {

    import type { BrowserConfig } from "@/lib/std/api";
    import type { CompiledConfig } from "@/lib/spec/surface";

    const browser: BrowserConfig & { realtime: CompiledConfig["realtime"] };

    export default browser;

}
