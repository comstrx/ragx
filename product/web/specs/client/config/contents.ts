import type { SiteConfig } from "@/lib/spec/surface";

export default {
    name: "RagX",
    tagline: "AI chat and human support, tenant by tenant",
    description: "RagX is a multi-tenant AI chat and human support platform that tenants integrate through the API.",
    copyright: null,
    url: "http://127.0.0.1:3000",
    logo: null,
    logo_dark: null,
    icon: "/images/brand/icon.svg",
    email: "hello@ragx.test",
    phone: null,
    address: null,
    links: [],
    socials: [{ name: "github", href: "https://github.com/comstrx/ragx" }],
    seo: {
        title: "RagX — AI chat and human support",
        description: "Multi-tenant AI chat with human handoff, RAG-ready, integrated through one API.",
        keywords: ["ai chat", "human support", "multi-tenant", "rag"],
        image: null,
        twitter: null,
        robots: { allow: ["/"], disallow: [] },
        verification: {},
    },
} satisfies SiteConfig["contents"];
