import { cpSync, existsSync, readFileSync, type Stats, statSync } from "node:fs";
import { dirname, extname, normalize, resolve, sep } from "node:path";
import process from "node:process";
import { brotliCompressSync, constants, gzipSync } from "node:zlib";
import { parseCookies } from "engine/cookie";
import { task } from "engine/tooling";
import { type Reserved, type Routing, routable, routeOf } from "engine/translate";
import { securityHeaders } from "./security.ts";

export type Served = { path: string; status: number } | null;
export type Built = {
    identity: string;
    output: "export" | "standalone";
    routing?: Routing | undefined;
    reserved?: Reserved | undefined;
    language?: string | undefined;
    connect?: string[] | undefined;
    media?: string[] | undefined;
    security?: Record<string, string> | undefined;
};
export type Address = { path: string } | { redirect: string; status: 307 | 308 };
export type Encoding = "br" | "gzip" | null;
export type Staged = { server: string; copied: string[] };

const root = resolve(import.meta.dir, "..");
const out = resolve(root, ".next/out");
const meta = resolve(root, "node_modules/.cache/spec/production/meta.json");
const year = "public, max-age=31536000, immutable";
const hour = "public, max-age=3600";
const fresh = "no-cache";
const varying = "Accept-Language, Cookie";
const packable = new Set([".html", ".js", ".css", ".json", ".svg", ".txt", ".xml", ".map", ".webmanifest"]);
const packFloor = 512;
const packCeiling = 4 * 1024 * 1024;
const packBudget = 64 * 1024 * 1024;
const packed = new Map<string, Uint8Array<ArrayBuffer>>();

let packedBytes = 0;

function file ( path: string ): boolean {

    return existsSync(path) && statSync(path).isFile();

}
export function candidates ( pathname: string ): string[] {

    const clean = normalize(decodeURIComponent(pathname)).replaceAll("\\", "/").replace(/\/+$/, "");
    const base = clean === "" ? "/index" : clean;

    return extname(base) ? [base] : [`${base}.html`, `${base}/index.html`];

}
export function locate ( folder: string, pathname: string ): Served {

    for ( const candidate of candidates(pathname) ) {

        const path = resolve(folder, `.${candidate}`);

        if ( !path.startsWith(folder + sep) ) return null;
        if ( file(path) ) return { path, status: 200 };

    }

    const missing = resolve(folder, "404.html");

    return file(missing) ? { path: missing, status: 404 } : null;

}
export function headersOf ( built: Built ): Record<string, string> {

    return built.security ?? securityHeaders(built);

}
export function headersFor ( path: string, status: number, security: Record<string, string> = securityHeaders({}) ): Record<string, string> {

    const html = path.endsWith(".html");
    const hashed = path.includes(`${sep}_next${sep}static${sep}`);
    const cache = html || status !== 200 ? fresh : hashed ? year : hour;

    return {
        ...security,
        "Cache-Control": cache,
        ...(packable.has(extname(path)) ? { Vary: "Accept-Encoding" } : {}),
    };

}
export function encodingFor ( accept: string | null ): Encoding {

    const offered = new Map<string, number>();

    for ( const part of (accept ?? "").split(",") ) {

        const [name = "", ...params] = part.trim().toLowerCase().split(";");
        const quality = params.map(( param ) => param.trim()).find(( param ) => param.startsWith("q="));

        offered.set(name, quality ? Number(quality.slice(2)) : 1);

    }

    if ( (offered.get("br") ?? 0) > 0 ) return "br";
    if ( (offered.get("gzip") ?? 0) > 0 ) return "gzip";

    return null;

}
export function packs ( path: string, size: number ): boolean {

    return packable.has(extname(path)) && size >= packFloor && size <= packCeiling;

}
export function pack ( bytes: Uint8Array, encoding: "br" | "gzip" ): Uint8Array<ArrayBuffer> {

    const quality = { [constants.BROTLI_PARAM_QUALITY]: 9, [constants.BROTLI_PARAM_SIZE_HINT]: bytes.byteLength };
    const squeezed = encoding === "br" ? brotliCompressSync(bytes, { params: quality }) : gzipSync(bytes, { level: 9 });

    return new Uint8Array(squeezed);

}
function tagOf ( stats: Stats, encoding: Encoding ): string {

    return `W/"${stats.size.toString(16)}-${Math.trunc(stats.mtimeMs).toString(16)}${encoding ? `-${encoding}` : ""}"`;

}
function packedBody ( path: string, stats: Stats, encoding: "br" | "gzip" ): Uint8Array<ArrayBuffer> {

    const key = `${path}|${stats.mtimeMs}|${stats.size}|${encoding}`;
    const known = packed.get(key);

    if ( known ) return known;

    const bytes = pack(readFileSync(path), encoding);

    if ( packedBytes + bytes.byteLength <= packBudget ) {

        packed.set(key, bytes);
        packedBytes += bytes.byteLength;

    }

    return bytes;

}
export function addressOf ( pathname: string, asked: Headers, built: Built ): Address {

    const { routing, reserved, language } = built;

    if ( !routing || !reserved || !routable(pathname, reserved) ) return { path: pathname };

    const saved = language ? parseCookies(asked.get("cookie"))[language] : undefined;
    const way = routeOf({ path: pathname, language: saved, accept: asked.get("accept-language") }, routing);

    if ( way.kind === "redirect" ) return { redirect: way.path, status: way.status };
    if ( way.kind === "pass" ) return { path: pathname };

    return { path: way.path.endsWith("/index.txt") ? `${way.path.slice(0, -"/index.txt".length)}.txt` : way.path };

}
export function respond ( folder: string, pathname: string, asked: Headers = new Headers(), security?: Record<string, string> ): Response {

    const found = locate(folder, pathname);

    if ( !found ) return new Response("Not Found", { status: 404, headers: headersFor("", 404, security) });

    const stats = statSync(found.path);
    const encoding = packs(found.path, stats.size) ? encodingFor(asked.get("accept-encoding")) : null;
    const tag = tagOf(stats, encoding);
    const headers = { ...headersFor(found.path, found.status, security), ETag: tag };

    if ( found.status === 200 && asked.get("if-none-match") === tag ) return new Response(null, { status: 304, headers });
    if ( !encoding ) return new Response(Bun.file(found.path), { status: found.status, headers });

    return new Response(packedBody(found.path, stats, encoding), {
        status: found.status,
        headers: { ...headers, "Content-Encoding": encoding, "Content-Type": Bun.file(found.path).type },
    });

}
function serverOf ( standalone: string ): string | undefined {

    if ( !existsSync(standalone) ) return undefined;

    const found = [...new Bun.Glob("**/server.js").scanSync({ cwd: standalone })].filter(( path ) => !path.includes("node_modules"));
    const [nearest] = found.sort(( a, b ) => a.length - b.length);

    return nearest === undefined ? undefined : resolve(standalone, nearest);

}
export function stage ( folder: string, publicFolder: string ): Staged {

    const standalone = resolve(folder, "standalone");
    const server = serverOf(standalone);

    if ( !server ) throw new Error(`There is no standalone server under ${standalone}; run bun run build first.`);

    const app = dirname(server);
    const copies: [string, string][] = [
        [publicFolder, resolve(app, "public")],
        [resolve(folder, "static"), resolve(app, ".next", "out", "static")],
    ];
    const copied = copies.flatMap(( [from, to] ) => {

        if ( !existsSync(from) || existsSync(to) ) return [];

        cpSync(from, to, { recursive: true, dereference: true });

        return [to];

    });

    return { server, copied };

}
function launch ( built: Built, port: number, hostname: string ): void {

    const { server } = stage(out, resolve(root, "public"));
    const child = Bun.spawn(["node", server], {
        stdio: ["inherit", "inherit", "inherit"],
        env: { ...process.env, PORT: String(port), HOSTNAME: hostname },
    });
    const stop = (): void => { child.kill("SIGTERM"); };

    process.on("SIGINT", stop);
    process.on("SIGTERM", stop);
    process.stdout.write(`Serving ${built.identity} from ${server} on http://${hostname}:${port}\n`);

    void child.exited.then(( code ) => { process.exitCode = code; });

}
function serve ( built: Built, port: number, hostname: string ): void {

    if ( !existsSync(out) ) throw new Error("There is no exported build to serve; run bun run build first.");

    const security = headersOf(built);
    const fetch = ( request: Request ): Response => {

        const url = new URL(request.url);
        const address = addressOf(url.pathname, request.headers, built);

        if ( "redirect" in address ) {

            const headers = { ...security, Location: `${address.redirect}${url.search}`, Vary: varying };

            return new Response(null, { status: address.status, headers });

        }

        const response = respond(out, address.path, request.headers, security);

        if ( address.path !== url.pathname ) response.headers.append("Vary", varying);

        return response;

    };

    Bun.serve({ port, hostname, fetch });
    process.stdout.write(`Serving ${built.identity} from ${out} on http://${hostname}:${port}\n`);

}

task(import.meta.url, () => {

    if ( !existsSync(meta) ) throw new Error("There is no compiled spec; run bun run build first.");

    const built = JSON.parse(readFileSync(meta, "utf8")) as Built;
    const port = Number(process.env.PORT ?? 3000);
    const hostname = process.env.HOSTNAME ?? "0.0.0.0";

    if ( built.output === "standalone" ) launch(built, port, hostname);
    else serve(built, port, hostname);

});
