"use client";

import Button from "@/elements/button";
import Notice from "@/elements/notice";
import { reportError } from "@/lib/observe/browser";
import { defineBoundary } from "@/lib/std/screen";

export const Boundary = defineBoundary<{ message?: string | undefined; retry?: string | undefined }>({
    report: reportError,
    fallback: ({ message, retry, reset }) => {

        if ( !message ) return null;

        const action = retry ? <Button tone="ghost" size="sm" onClick={reset}>{retry}</Button> : undefined;

        return <Notice tone="failed" message={message} action={action} />;

    },
});
