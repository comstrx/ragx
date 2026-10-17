import { feature, get } from "@/lib/std/api";
import { z } from "@/lib/std/validate";

const greeting = z.object({ message: z.string() });
const name = z.string().min(1).max(32).optional();

export default feature({ cache: 30 }, {
    read: get("/hello", { name }, greeting),
});
