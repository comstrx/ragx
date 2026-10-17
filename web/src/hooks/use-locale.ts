"use client";

import { useParams } from "next/navigation";
import { routing } from "@/lib/spec/config";
import type { Locale } from "@/lib/spec/languages";
import { choose } from "@/lib/std/base";

export function useLocale (): Locale {

    const params = useParams<{ locale?: string }>();

    return choose(routing.locales, params?.locale, routing.defaultLocale);

}
