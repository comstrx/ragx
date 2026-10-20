import { describe, expect, test } from "bun:test";
import { defineStore } from "@/lib/std/state";
import { memoryStore } from "@/lib/std/storage";

type Session = { token: string | null; user: { id: number } | null };

const session = ( store = memoryStore() ) =>
    defineStore({
        name: "session",
        initial: { token: null, user: null } as Session,
        actions: ( set ) => ({
            start: ( token: string, user: { id: number } ) => set({ token, user }),
            end: () => set({ token: null, user: null }),
        }),
        persist: {
            store,
            keys: ["token", "user"],
            parse: ( saved ) => (typeof (saved as Session).token === "string" ? (saved as Partial<Session>) : undefined),
        },
    });

describe("store", () => {

    test("a store instance acts, persists chosen keys and hydrates on a fresh instance", async () => {

        const store = memoryStore();
        const defined = session(store);
        const first = defined.create();

        await first.hydrate();
        first.getState().start("t", { id: 1 });
        await new Promise(( resolve ) => setTimeout(resolve, 0));
        expect(JSON.parse((await store.get("session")) ?? "{}")).toEqual({
            version: 1,
            state: { token: "t", user: { id: 1 } },
        });

        const second = defined.create();

        expect(second.getState().ready).toBe(false);
        await second.hydrate();
        expect(second.getState().token).toBe("t");
        second.getState().end();
        expect(second.getState().user).toBeNull();

    });
    test("a saved value the parser refuses is ignored", async () => {

        const store = memoryStore();

        await store.set("session", JSON.stringify({ version: 1, state: { token: 7, user: null } }));

        const instance = session(store).create();

        await instance.hydrate();
        expect(instance.getState().token).toBeNull();
        expect(instance.getState().ready).toBe(true);

    });
    test("field persistence keeps one raw entry per field, writes only what changed from the defaults and refuses a bad saved value", async () => {

        const store = memoryStore();
        const prefs = defineStore({
            name: "prefs",
            initial: { language: "en", theme: "light" },
            actions: ( set ) => ({ choose: ( language: string ) => set({ language }) }),
            persist: {
                store,
                keys: ["language", "theme"],
                fields: true,
                parse: ( saved ) => ((saved as { theme?: string }).theme === "sepia" ? { language: "en" } : (saved as { language: string })),
            },
        });
        const first = prefs.create();
        const settle = () => new Promise(( resolve ) => setTimeout(resolve, 0));

        await first.hydrate();
        await settle();
        expect(await store.keys()).toEqual([]);

        first.getState().choose("ar");
        await settle();
        expect(await store.keys()).toEqual(["language"]);
        expect(await store.get("language")).toBe("ar");

        const second = prefs.create();

        await second.hydrate();
        expect(second.getState().language).toBe("ar");

        await store.set("theme", "sepia");

        const third = prefs.create();

        await third.hydrate();
        expect(third.getState()).toMatchObject({ language: "en", theme: "light" });

    });

});
