import type { ManifestInput } from "@/lib/std/spec";

export default {
    owner: "client",
    options: { fallback: "", live: "", saved: "", loading: "", failed: "", offline: "", cached: "" },
    ports: { greeting: { kind: "one", fields: ["message"], required: false } },
} satisfies ManifestInput;
