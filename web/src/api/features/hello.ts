import { feature, get } from "@/lib/std/api";
import { contract } from "@/lib/std/spec";
import { z } from "@/lib/std/validate";

const greeting = z.object({ message: z.string() });
const name = z.string().min(1).max(32).optional();

export default contract({
    transport: feature({ cache: 30 }, {
        read: get("/hello", { name }, greeting),
    }),
    view: {
        owner: "client",
        options: { fallback: "", live: "", saved: "", loading: "", failed: "", offline: "", cached: "" },
        ports: { greeting: { kind: "one", fields: ["message"], required: false } },
    },
});
