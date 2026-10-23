import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { classes, variants } from "engine/style";
import { classIssues } from "../tools/core.ts";

describe("style", () => {

    test("classes keep the given order and drop every empty, false or missing part", () => {

        expect(classes("a", false, null, undefined, "", "b c")).toBe("a b c");
        expect(classes()).toBe("");

    });
    test("a look applies its defaults, lets a choice override one axis, accepts numeric keys and answers the same string twice", () => {

        const look = variants("base", { size: { sm: "h-8", md: "h-10" }, level: { 1: "text-2xl", 2: "text-xl" } }, { size: "md", level: "1" });
        const first = look({ size: "sm" });

        expect(look()).toBe("base h-10 text-2xl");
        expect(first).toBe("base h-8 text-2xl");
        expect(look({ level: "2" })).toBe("base h-10 text-xl");
        expect(look({ size: "sm" })).toBe(first);

    });
    test("an element class may name tokens only: a raw arbitrary value or an opacity modifier is refused", () => {

        const root = mkdtempSync(join(tmpdir(), "web-classes-"));

        mkdirSync(join(root, "elements"), { recursive: true });
        writeFileSync(join(root, "elements", "clean.tsx"), 'const a = "p-4 duration-(--motion-fast) transition-[color,translate] bg-hover";\n');
        writeFileSync(join(root, "elements", "raw.tsx"), 'const a = "w-[13px] bg-[#ff0000]";\nconst b = "bg-primary/40 text-ink";\n');

        expect(classIssues(root)).toEqual([
            "src/elements/raw.tsx:1: a raw value belongs in tokens.css, not in a class: w-[13px]",
            "src/elements/raw.tsx:1: a raw value belongs in tokens.css, not in a class: bg-[#ff0000]",
            "src/elements/raw.tsx:2: a raw value belongs in tokens.css, not in a class: bg-primary/40",
        ]);

    });

});
