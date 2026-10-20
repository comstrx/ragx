"use client";

import Button from "@/elements/button";
import Notice from "@/elements/notice";
import { useLocale } from "@/hooks/use-locale";
import { text } from "@/lib/spec/runtime";

type Props = { error: Error & { digest?: string }; reset: () => void };

export default function Failure ({ error, reset }: Props) {

    const locale = useLocale();
    const retry = <Button tone="ghost" size="sm" onClick={reset}>{text({ key: "state.retry" }, locale)}</Button>;

    return <Notice tone="failed" message={text({ key: "state.failed" }, locale)} action={retry} digest={error.digest} />;

}
