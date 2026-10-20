"use client";

import Notice from "@/elements/notice";
import { useLocale } from "@/hooks/use-locale";
import { text } from "@/lib/spec/runtime";

export function Missing () {

    const locale = useLocale();

    return <Notice tone="missing" message={text({ key: "state.missing" }, locale)} />;

}
