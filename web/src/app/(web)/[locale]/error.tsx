"use client";

import Notice from "@/elements/notice";
import { useLocale } from "@/hooks/use-locale";
import { text } from "@/lib/spec/runtime";

type Props = { error: Error & { digest?: string }; reset: () => void };

export default function Failure ({ error, reset }: Props) {

    const locale = useLocale();

    return (

        <Notice
            tone="failed"
            message={text({ key: "state.failed" }, locale)}
            action={text({ key: "state.retry" }, locale)}
            onAction={reset}
            digest={error.digest}
        />

    );

}
