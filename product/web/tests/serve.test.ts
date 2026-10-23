import { describe, expect, test } from "bun:test";
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { brotliDecompressSync, gunzipSync } from "node:zlib";
import { policy, securityHeaders } from "../tools/security.ts";
import { candidates, encodingFor, headersFor, headersOf, locate, respond, stage } from "../tools/serve.ts";

const out = mkdtempSync(join(tmpdir(), "web-out-"));

mkdirSync(join(out, "en", "settings"), { recursive: true });
mkdirSync(join(out, "_next", "static", "chunks"), { recursive: true });
writeFileSync(join(out, "index.html"), "<!doctype html>root");
writeFileSync(join(out, "en.html"), "<!doctype html>en");
writeFileSync(join(out, "en", "settings", "index.html"), "<!doctype html>settings");
writeFileSync(join(out, "404.html"), "<!doctype html>missing");
writeFileSync(join(out, "_next", "static", "chunks", "app.js"), "export {};");
writeFileSync(join(out, "en", "report.html"), `<!doctype html>${"report ".repeat(200)}`);

describe("the static release server", () => {

    test("a clean path resolves to its html twin or its folder index, in that order", () => {

        expect(candidates("/")).toEqual(["/index.html", "/index/index.html"]);
        expect(candidates("/en")).toEqual(["/en.html", "/en/index.html"]);
        expect(candidates("/en/settings/")).toEqual(["/en/settings.html", "/en/settings/index.html"]);
        expect(candidates("/_next/static/chunks/app.js")).toEqual(["/_next/static/chunks/app.js"]);

    });
    test("every exported shell is found and an unknown path answers the 404 shell with its status", () => {

        expect(locate(out, "/")?.status).toBe(200);
        expect(locate(out, "/en")?.path.endsWith("en.html")).toBe(true);
        expect(locate(out, "/en/settings")?.path.endsWith("settings/index.html")).toBe(true);
        expect(locate(out, "/en/nowhere")).toEqual({ path: join(out, "404.html"), status: 404 });

    });
    test("a path can never climb out of the export folder", () => {

        expect(locate(out, "/../../etc/passwd")?.status).not.toBe(200);
        expect(locate(out, "/en/%2e%2e/%2e%2e/etc/passwd")?.status).not.toBe(200);

    });
    test("html is never cached, hashed assets are cached for a year, and every answer carries the security headers", async () => {

        const page = headersFor(join(out, "en.html"), 200);
        const chunk = headersFor(join(out, "_next", "static", "chunks", "app.js"), 200);
        const generated = headersFor(join(out, "_generated", "boot.js"), 200);

        expect(page["Cache-Control"]).toBe("no-cache");
        expect(chunk["Cache-Control"]).toContain("immutable");
        expect(generated["Cache-Control"]).not.toContain("immutable");
        expect(page["X-Frame-Options"]).toBe("DENY");
        expect(chunk["X-Content-Type-Options"]).toBe("nosniff");
        expect(page["Content-Security-Policy"]).toContain("default-src 'self'");

        const missing = respond(out, "/en/nowhere");

        expect(missing.status).toBe(404);
        expect(await missing.text()).toContain("missing");

    });
    test("the browser's encodings are honored in order of strength and a refused one is skipped", () => {

        expect(encodingFor("gzip, deflate, br")).toBe("br");
        expect(encodingFor("gzip;q=1.0, br;q=0")).toBe("gzip");
        expect(encodingFor("identity")).toBeNull();
        expect(encodingFor(null)).toBeNull();

    });
    test("a text answer large enough is packed for the browser, decompresses to the file and keeps its type; small ones go plain", async () => {

        const br = respond(out, "/en/report", new Headers({ "accept-encoding": "br" }));
        const gzip = respond(out, "/en/report", new Headers({ "accept-encoding": "gzip" }));
        const plain = respond(out, "/en", new Headers({ "accept-encoding": "br" }));

        expect(br.headers.get("Content-Encoding")).toBe("br");
        expect(br.headers.get("Vary")).toBe("Accept-Encoding");
        expect(br.headers.get("Content-Type")).toContain("text/html");
        expect(Buffer.from(brotliDecompressSync(await br.bytes())).toString()).toContain("report report");
        expect(Buffer.from(gunzipSync(await gzip.bytes())).toString()).toContain("report report");
        expect(plain.headers.get("Content-Encoding")).toBeNull();
        expect(await plain.text()).toBe("<!doctype html>en");

    });
    test("every answer carries a weak validator; a matching one turns a 200 into 304 but never the 404 shell", () => {

        const first = respond(out, "/en");
        const tag = first.headers.get("ETag") ?? "";
        const again = respond(out, "/en", new Headers({ "if-none-match": tag }));
        const gone = respond(out, "/en/nowhere").headers.get("ETag") ?? "";
        const missing = respond(out, "/en/nowhere", new Headers({ "if-none-match": gone }));

        expect(tag.startsWith('W/"')).toBe(true);
        expect(again.status).toBe(304);
        expect(again.headers.get("Cache-Control")).toBe("no-cache");
        expect(missing.status).toBe(404);

    });
    test("the content policy locks the page to itself, opens connections only to the api, and rides on every answer", () => {

        const csp = policy({ connect: ["https://api.example.test"], media: ["https://cdn.example.test"] });
        const headers = securityHeaders({ connect: ["https://api.example.test"], media: ["https://cdn.example.test"] });

        expect(csp).toContain("connect-src 'self' https://api.example.test");
        expect(csp).toContain("img-src 'self' data: blob: https://cdn.example.test");
        expect(csp).toContain("frame-ancestors 'none'");
        expect(headers["Content-Security-Policy"]).toBe(csp);
        expect(respond(out, "/en", new Headers(), headers).headers.get("Content-Security-Policy")).toBe(csp);
        expect(respond(out, "/no/such", new Headers(), headers).headers.get("Content-Security-Policy")).toBe(csp);

    });
    test("the compiled security headers win over the computed ones, and an export without them still gets the fixed set", () => {

        const compiled = { identity: "site", output: "export" as const, security: { "X-Frame-Options": "SAMEORIGIN" } };

        expect(headersOf(compiled)).toEqual({ "X-Frame-Options": "SAMEORIGIN" });
        expect(headersOf({ identity: "site", output: "export", connect: ["https://api.example.test"] })["Content-Security-Policy"])
            .toContain("https://api.example.test");

    });
    test("a standalone build is staged by copying public and the static chunks beside its traced server, and refused without one", () => {

        const folder = mkdtempSync(join(tmpdir(), "web-standalone-"));
        const publicFolder = join(folder, "public");
        const app = join(folder, "standalone", "product", "web");

        expect(() => stage(folder, publicFolder)).toThrow("no standalone server");

        mkdirSync(join(folder, "standalone", "node_modules", "next"), { recursive: true });
        mkdirSync(app, { recursive: true });
        mkdirSync(join(folder, "static", "chunks"), { recursive: true });
        mkdirSync(join(publicFolder, "images"), { recursive: true });
        writeFileSync(join(folder, "standalone", "node_modules", "next", "server.js"), "");
        writeFileSync(join(app, "server.js"), "");
        writeFileSync(join(folder, "static", "chunks", "app.js"), "export {};");
        writeFileSync(join(publicFolder, "images", "logo.svg"), "<svg/>");

        const staged = stage(folder, publicFolder);

        expect(staged.server).toBe(join(app, "server.js"));
        expect(staged.copied).toHaveLength(2);
        expect(existsSync(join(app, "public", "images", "logo.svg"))).toBe(true);
        expect(existsSync(join(app, ".next", "out", "static", "chunks", "app.js"))).toBe(true);

    });

});
