import { existsSync, readFileSync, realpathSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve, sep } from "node:path";
import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js";

type Meta = {
    identity: string;
    output: "export" | "standalone";
    indexed: number;
    secure: boolean;
    insecure: boolean;
    media: string[];
    security: Record<string, string>;
    aliases: Record<string, string>;
};

const root = import.meta.dirname;
const engine = dirname(realpathSync(createRequire(import.meta.url).resolve("engine/package.json")));
const pages = ["tsx", "ts"];
const served = ["server.tsx", "server.ts", ...pages];

function shared ( a: string, b: string ): string {
    const left = a.split(sep);
    const right = b.split(sep);
    const length = left.findIndex(( part, index ) => part !== right[index]);

    return left.slice(0, length === -1 ? left.length : length).join(sep) || sep;
}
function compiled ( mode: "development" | "production" ): Meta {
    const path = resolve(root, "node_modules/.cache/spec", mode, "meta.json");

    if ( !existsSync(path) ) throw new Error(`No compiled spec for ${mode}: run \`bun tools/compile.ts ${mode}\` first.`);

    return JSON.parse(readFileSync(path, "utf8")) as Meta;
}
function guarded ( spec: Meta, development: boolean ): Pick<NextConfig, "headers"> {
    if ( spec.output !== "standalone" || development ) return {};

    const headers = Object.entries(spec.security).map(( [key, value] ) => ({ key, value }));

    return { headers: () => Promise.resolve([{ source: "/:path*", headers }]) };
}
export default function nextConfig ( phase: string ): NextConfig {
    const development = phase === PHASE_DEVELOPMENT_SERVER;
    const spec = compiled(development ? "development" : "production");
    const devOrigins = (process.env.NEXT_DEV_ORIGINS ?? "").split(/[\s,]+/).filter(Boolean);
    const exported = spec.output === "export" && !development;
    const workspace = shared(root, engine);

    return {
        ...(development ? {} : { output: spec.output }),
        distDir: ".next/out",
        pageExtensions: exported ? pages : served,
        trailingSlash: false,
        productionBrowserSourceMaps: false,
        reactCompiler: true,
        experimental: { staleTimes: { dynamic: 30, static: 180 } },
        typedRoutes: true,
        poweredByHeader: false,
        agentRules: false,
        images: { unoptimized: true, remotePatterns: spec.media.map(( origin ) => new URL(`${origin}/**`)) },
        env: { NEXT_PUBLIC_SPEC: spec.identity },
        transpilePackages: ["engine"],
        outputFileTracingRoot: workspace,
        turbopack: { root: workspace, resolveAlias: spec.aliases },
        ...guarded(spec, development),
        ...(development && devOrigins.length ? { allowedDevOrigins: devOrigins } : {}),
    };
}
