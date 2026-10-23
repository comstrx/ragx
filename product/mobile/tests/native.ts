import { mock } from "bun:test";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { plugin } from "bun";

type Meta = { identity: string; aliases: Record<string, string> };

const root = resolve(import.meta.dir, "..");
const engine = dirname(realpathSync(Bun.resolveSync("engine/package.json", root)));
const meta = resolve(root, "node_modules/.cache/spec/production/meta.json");
const assets = /\.(?:webp|png|jpe?g|gif|svg|ttf|otf|mp3|mp4|wav)$/;
const hosts = ["react", "react/jsx-runtime", "react/jsx-dev-runtime", "react-dom", "react-dom/server"];

if ( !existsSync(meta) ) throw new Error("No compiled spec for production: run `bun tools/compile.ts production` first.");

const compiled = JSON.parse(readFileSync(meta, "utf8")) as Meta;

function load ( path: string ): Record<string, unknown> {

    if ( path.endsWith(".json") ) return { default: JSON.parse(readFileSync(path, "utf8")) as unknown };

    const found = require(path) as Record<string, unknown>;

    return { ...found, default: found.default ?? found };

}

mock.module("react-native", () => load(Bun.resolveSync("react-native-web", root)));

for ( const host of hosts ) mock.module(Bun.resolveSync(host, engine), () => load(Bun.resolveSync(host, root)));
for ( const [name, path] of Object.entries(compiled.aliases) ) mock.module(name, () => load(resolve(root, path)));

mock.module("expo-constants", () => ({ default: { expoConfig: { extra: { spec: compiled.identity } } } }));

plugin({
    name: "metro assets",
    setup ( build ) {

        build.onLoad({ filter: assets }, ( args ) => ({ contents: `export default ${JSON.stringify(args.path)};`, loader: "js" }));

    },
});
