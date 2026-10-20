"use client";

import views from "@spec/mount";
import { type ReadonlyURLSearchParams, usePathname, useSearchParams } from "next/navigation";
import { createElement, useEffect } from "react";
import type { FeatureProps, Route } from "@/lib/spec/feature";

type Props = FeatureProps & { name: string };

const intents = ["pointerdown", "pointermove", "touchstart", "keydown", "click", "scroll"] as const;

let engaged = false;

function queryOf ( search: ReadonlyURLSearchParams ): Route["query"] {

    return Object.fromEntries([...search.keys()].map(( key ) => {

        const all = search.getAll(key);

        return [key, all.length > 1 ? all : (all[0] ?? undefined)];

    }));

}
function whenIdle ( run: () => void ): () => void {

    if ( typeof requestIdleCallback !== "function" ) {

        const timer = window.setTimeout(run, 200);

        return () => window.clearTimeout(timer);

    }

    const handle = requestIdleCallback(run);

    return () => cancelIdleCallback(handle);

}
function onIntent ( run: () => void ): () => void {

    let timer = 0;

    if ( engaged ) { run(); return () => undefined; }

    const start = (): void => {

        engaged = true;

        stop();

        timer = window.setTimeout(run, 500);

    };
    const stop = (): void => {

        for ( const name of intents ) {

            window.removeEventListener(name, start, true);

        }

    };

    for ( const name of intents ) {

        window.addEventListener(name, start, { capture: true, passive: true });

    }
    return () => {

        stop();
        window.clearTimeout(timer);

    };

}
export function Mount ({ name, route, ...props }: Props) {

    const search = useSearchParams();
    const View = views[name];

    if ( !View ) throw new Error(`No client feature named ${name}.`);

    const query = Object.keys(route.query).length ? route.query : queryOf(search);

    return createElement(View, { ...props, route: { ...route, query } });

}
export function Preload () {

    const pathname = usePathname();

    useEffect(() => {

        if ( (navigator as { connection?: { saveData?: boolean } }).connection?.saveData ) return;

        let cancel = (): void => undefined;

        const warm = (): void => { void import("./warm.ts").then(( module ) => module.warm(pathname)).catch(() => undefined); };
        const stop = onIntent(() => { cancel = whenIdle(warm); });

        return () => { stop(); cancel(); };

    }, [pathname]);

    return null;

}
