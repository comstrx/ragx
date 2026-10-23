"use client";

import { choose } from "engine/base";
import { useParams } from "next/navigation";
import { routing } from "@/lib/spec/config";
import type { Locale } from "@/lib/spec/languages";

export function useLocale (): Locale {

    const params = useParams<{ locale?: string }>();

    return choose(routing.locales, params?.locale, routing.defaultLocale);

}
