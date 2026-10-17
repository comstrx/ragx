import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { lineIssues } from "../tools/core.ts";

const folder = mkdtempSync(join(tmpdir(), "web-lines-"));

mkdirSync(join(folder, "lib", "std", "world", "data"), { recursive: true });
writeFileSync(join(folder, "short.ts"), "const a = 1;\n");
writeFileSync(join(folder, "wide.tsx"), `const b = "${"x".repeat(160)}";\nconst c = 2;\n`);
writeFileSync(join(folder, "wide.md"), "x".repeat(400));
writeFileSync(join(folder, "lib", "std", "world", "data", "wide.ts"), "x".repeat(400));

describe("the line law", () => {

    test("a source line wider than the law is named with its file and line; prose and the world data are not measured", () => {

        expect(lineIssues(folder, "src", 150)).toEqual(["src/wide.tsx:1: 173 columns; the law is 150."]);
        expect(lineIssues(folder, "src", 200)).toEqual([]);

    });

});
