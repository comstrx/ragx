"use client";

import Notice from "@/elements/notice";
import { reportError } from "@/lib/observe/browser";
import { defineBoundary } from "@/lib/std/screen";

export const Boundary = defineBoundary<{ message?: string | undefined; retry?: string | undefined }>({
    report: reportError,
    fallback: ({ message, retry, reset }) => (message ? <Notice tone="failed" message={message} action={retry} onAction={reset} /> : null),
});
