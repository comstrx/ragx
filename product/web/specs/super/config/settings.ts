import type { SiteConfig } from "@/lib/spec/surface";

export default {
    output: "export",
    theme: { default: "system" },
    mediaOrigins: ["http://127.0.0.1:8000"],
    screen: {
        nav: false,
        sidebar: false,
    },
} satisfies SiteConfig["settings"];
