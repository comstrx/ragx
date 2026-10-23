import { feature, get } from "engine/api";
import { contract } from "engine/spec";
import { z } from "engine/validate";

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
