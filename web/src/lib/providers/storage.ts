import { lazyStore, memoryStore, type Store, webStore } from "@/lib/std/storage";

export const session: Store = lazyStore(() => (typeof sessionStorage === "undefined" ? memoryStore() : webStore(sessionStorage)));
export const persistent: Store = lazyStore(() => (typeof localStorage === "undefined" ? memoryStore() : webStore(localStorage)));
