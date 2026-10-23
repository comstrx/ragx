import type { Reserved } from "engine/translate";

export const reserved = {
    roots: ["_next", "_generated", "images", "fonts", "videos", "audios", ".well-known"],
    files: ["/manifest.webmanifest", "/robots.txt", "/sitemap.xml", "/favicon.ico", "/404.html"],
} as const satisfies Reserved;
