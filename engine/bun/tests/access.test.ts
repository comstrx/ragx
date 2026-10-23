import { describe, expect, test } from "bun:test";
import { allowed, connectionOrigins, del, feature, get, many, missing, need } from "engine/api";
import { z } from "engine/validate";

describe("permissions", () => {

    test("an operation names what it needs, the group adds its own, and a holder is checked against both", () => {

        const group = feature(
            { permissions: ["user"] },
            {
                remove: need(["delete_items"], del("/items/{id}", { id: z.number() }, z.unknown())),
                list: get("/items", {}, many(z.object({ id: z.number() }))),
            },
        );

        expect(group.remove.permissions).toEqual(["user", "delete_items"]);
        expect(group.list.permissions).toEqual(["user"]);
        expect(allowed({ permissions: ["delete_items"] }, group.remove.permissions)).toBe(true);
        expect(allowed({ permissions: [] }, group.remove.permissions)).toBe(false);
        expect(allowed(null, ["user"])).toBe(false);
        expect(missing({ permissions: [] }, group.remove.permissions)).toEqual(["delete_items"]);

    });

});
describe("connection origins", () => {

    test("every connection with an address names its origin once, and a part without a backend has none", () => {

        const api = {
            connections: {
                primary: { baseUrl: "https://api.example.test/v1" },
                files: { baseUrl: "https://api.example.test/files" },
                idle: { baseUrl: null },
            },
        };

        expect(connectionOrigins(api)).toEqual(["https://api.example.test"]);
        expect(connectionOrigins(null)).toEqual([]);

    });

});
