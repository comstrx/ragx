import type { Layer } from "engine/api";

export const core: Layer = {};

export const reasons = [
    "ok", "created", "accepted", "bad_request", "unauthorized", "forbidden", "not_found", "method_not_allowed",
    "conflict", "validation", "too_many_requests", "internal", "unavailable",
] as const;
