"use client";

import Greeting from "@/components/greeting";
import type { FeatureProps } from "@/lib/spec/feature";
import { useGreeting } from "../hooks/use-greeting.ts";

export type Options = {
    fallback: string;
    live: string;
    saved: string;
    loading: string;
    failed: string;
    offline: string;
    cached: string;
};

export default function Welcome ({ options, ports, route, feature }: FeatureProps<Options>) {

    const greeting = useGreeting(ports, route, options.fallback);
    const primary  = feature?.heading ?? true;
    const id       = feature?.slug ?? "hello";

    if ( greeting.status !== "ready" ) {

        const waiting = greeting.status === "loading";

        return (
            <Greeting
                id={id}
                message={options.fallback}
                note={waiting ? options.loading : options.failed}
                tone={waiting ? "default" : "warning"}
                primary={primary}
            />
        );

    }

    const note = greeting.live ? (greeting.stale ? options.saved : options.live) : options.offline;

    return <Greeting id={id} message={greeting.message} note={note} tone={greeting.live ? "success" : "warning"} primary={primary} />;

}
