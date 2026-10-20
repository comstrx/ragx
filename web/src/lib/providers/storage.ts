import { documentJar, jarStore } from "@/lib/std/cookie";
import { lazyStore, memoryStore, type Store, webStore } from "@/lib/std/storage";

const year = 365 * 24 * 60 * 60;

export const session: Store = lazyStore(() => (typeof sessionStorage === "undefined" ? memoryStore() : webStore(sessionStorage)));
export const persistent: Store = lazyStore(() => (typeof localStorage === "undefined" ? memoryStore() : webStore(localStorage)));
export const cookies: Store = lazyStore(() =>
    typeof document === "undefined"
        ? memoryStore()
        : jarStore(documentJar(document), { maxAge: year, sameSite: "lax", secure: location.protocol === "https:" }),
);
