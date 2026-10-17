import { contentSecurityPolicy } from "@/lib/std/net";

export type Reach = { connect?: readonly string[] | undefined; media?: readonly string[] | undefined };

export const fixedHeaders = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
} as const;

export function policy ( reach: Reach ): string {

    const media = ["'self'", "data:", "blob:", ...(reach.media ?? [])];

    return contentSecurityPolicy({
        "default-src": ["'self'"],
        "script-src": ["'self'", "'unsafe-inline'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": media,
        "media-src": media,
        "font-src": ["'self'", "data:"],
        "connect-src": ["'self'", ...(reach.connect ?? [])],
        "frame-ancestors": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "object-src": ["'none'"],
    });

}
export function securityHeaders ( reach: Reach ): Record<string, string> {

    return { ...fixedHeaders, "Content-Security-Policy": policy(reach) };

}
