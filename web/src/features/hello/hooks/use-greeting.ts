"use client";

import { usePort } from "@/hooks/use-client";
import type { Ports, Route } from "@/lib/spec/feature";
import { field, row, touched } from "@/lib/std/client";

export type Greeting =
    | { status: "loading" }
    | { status: "failed"; retry: () => void }
    | { status: "ready"; message: string; live: boolean; stale: boolean };

export function useGreeting ( ports: Ports, route: Route, fallback: string ): Greeting {

    const port = ports.greeting;
    const resource = usePort(port, route);

    if ( resource.status === "failed" ) return { status: "failed", retry: () => touched(port?.kind === "read" ? [port.feature] : []) };
    if ( resource.status !== "ready" ) return { status: "loading" };

    const message = field(row(resource.value), "message");

    return { status: "ready", message: message ?? fallback, live: message !== undefined, stale: resource.stale === true };

}
