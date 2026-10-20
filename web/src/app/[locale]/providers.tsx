"use client";

import type { ReactNode } from "react";
import { SessionProvider, SignalsProvider } from "@/hooks/use-client";
import { PreferencesProvider, useTheme } from "@/hooks/use-preferences";

function Theme () {

    useTheme();

    return null;

}
export function Providers ({ children }: { children: ReactNode }) {

    return (

        <PreferencesProvider>

            <Theme />

            <SessionProvider><SignalsProvider>{children}</SignalsProvider></SessionProvider>

        </PreferencesProvider>

    );

}
