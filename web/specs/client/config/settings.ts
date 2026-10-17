import type { SiteConfig } from "@/lib/spec/surface";

export default {
    output: "standalone",
    mediaOrigins: ["http://127.0.0.1:8000"],
    screen: {
        render: "server",
        nav: false,
        sidebar: false,
    },
} satisfies SiteConfig["settings"];
