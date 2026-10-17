"use client";

import { type ReactNode, useSyncExternalStore } from "react";

type Props = { children: ReactNode; fallback?: ReactNode };

const subscribe = (): (() => void) => () => undefined;

export function ClientOnly ({ children, fallback = null }: Props) {

    const mounted = useSyncExternalStore(subscribe, () => true, () => false);

    return mounted ? children : fallback;

}
