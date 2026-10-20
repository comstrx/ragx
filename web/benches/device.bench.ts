import { createDevice, webAdapter } from "@/lib/std/device";
import { bench, do_not_optimize, measured  } from "@/lib/std/tooling";

const device = createDevice(webAdapter({ navigator: { userAgent: "Mozilla/5.0 (X11; Linux x86_64) Chrome/142.0", language: "en" } }));

bench("device.info", () => do_not_optimize(device.info()));

await measured({
    "device.info": 5,
});
