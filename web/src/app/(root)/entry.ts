"use client";

import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { preferences, routing } from "@/lib/spec/config";
import { choose } from "@/lib/std/base";
import { negotiate } from "@/lib/std/translate";

function saved (): string | undefined {

    try { return JSON.parse(localStorage.getItem(preferences.keys.language) ?? "null") as string | undefined; }
    catch { return undefined; }

}
export function Entry () {

    const router = useRouter();

    useEffect(() => {

        const preferred = saved() ?? negotiate(navigator.languages.join(","), routing.locales);

        router.replace(`/${choose(routing.locales, preferred, routing.defaultLocale)}` as Route);

    }, [router]);

    return null;

}
