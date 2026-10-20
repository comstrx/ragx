import { describe, expect, test } from "bun:test";
import { edgesOf, indexOf, stepOf, strideOf } from "@/lib/std/interact";
import { isCurrent, titled, titleOf } from "@/lib/std/screen";
import { switched } from "@/lib/std/translate";

const localized = { locales: ["en", "ar"], defaultLocale: "en", localized: true };

describe("interaction", () => {

    test("overflow edges read the scrolled distance on either side, so a right-to-left strip reports the same edges", () => {

        expect(edgesOf(0, 300, 300)).toEqual({ start: false, end: false });
        expect(edgesOf(0, 300, 900)).toEqual({ start: false, end: true });
        expect(edgesOf(300, 300, 900)).toEqual({ start: true, end: true });
        expect(edgesOf(600, 300, 900)).toEqual({ start: true, end: false });
        expect(edgesOf(-600, 300, 900)).toEqual({ start: true, end: false });
        expect(edgesOf(0.5, 300, 300.5)).toEqual({ start: false, end: false });

    });
    test("a scroll stride is most of the visible width, signed by the direction and the writing mode", () => {

        expect(strideOf("end", 500, false)).toBe(400);
        expect(strideOf("start", 500, false)).toBe(-400);
        expect(strideOf("end", 500, true)).toBe(-400);
        expect(strideOf("start", 500, true)).toBe(400);

    });
    test("roving keys move along the axis, flip on a right-to-left row, jump to the ends and wrap around", () => {

        expect(stepOf("ArrowRight", "horizontal", false)).toBe(1);
        expect(stepOf("ArrowRight", "horizontal", true)).toBe(-1);
        expect(stepOf("ArrowDown", "vertical", true)).toBe(1);
        expect(stepOf("ArrowDown", "horizontal", false)).toBeNull();
        expect(stepOf("Home", "vertical", false)).toBe("first");
        expect(stepOf("End", "horizontal", true)).toBe("last");
        expect([indexOf(4, 1, 5), indexOf(0, -1, 5), indexOf(2, "first", 5), indexOf(2, "last", 5)]).toEqual([0, 4, 0, 4]);
        expect([indexOf(-1, 1, 5), indexOf(-1, -1, 5)]).toEqual([0, 4]);

    });

});
describe("document", () => {

    test("a title joins action, page and project with the one separator and skips empty parts", () => {

        const target = { title: "" };

        expect(titleOf(["Active", "Items", "RagX"])).toBe("Active | Items | RagX");
        expect(titleOf([undefined, "Items", " ", null, "RagX"])).toBe("Items | RagX");
        expect(titled(target, ["General", "Settings", "RagX"])).toBe("General | Settings | RagX");
        expect(target.title).toBe("General | Settings | RagX");

    });
    test("a link is current on its own path and below it, except home which is current only on itself", () => {

        expect(isCurrent("/items", "/items", "/")).toBe(true);
        expect(isCurrent("/items/7", "/items", "/")).toBe(true);
        expect(isCurrent("/items/", "/items", "/")).toBe(true);
        expect(isCurrent("/itemsx", "/items", "/")).toBe(false);
        expect(isCurrent("/items", "/", "/")).toBe(false);
        expect(isCurrent("/", "/", "/")).toBe(true);
        expect(isCurrent("/en/items", "/en", "/en")).toBe(false);

    });
    test("switching language moves a localized url to the other prefix and leaves an unlocalized one in place", () => {

        expect(switched("/en/items", "ar", localized)).toBe("/ar/items");
        expect(switched("/en", "ar", localized)).toBe("/ar");
        expect(switched("/items", "ar", { ...localized, localized: false })).toBeNull();

    });

});
