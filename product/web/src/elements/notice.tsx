import { variants } from "engine/style";
import type { ReactNode } from "react";

type Props = {
    tone: "missing" | "failed" | "offline";
    message: string;
    action?: ReactNode | undefined;
    digest?: string | undefined;
};

const look = variants(
    "mx-auto my-6 flex w-full max-w-narrow animate-enter flex-col items-center gap-3 rounded-panel-lg border bg-panel p-4 shadow-panel-sm",
    { tone: { missing: "border-line", failed: "border-danger-edge", offline: "border-warning-edge" } },
    { tone: "missing" },
);

export default function Notice ({ tone, message, action, digest }: Props) {

    return (

        <section className={look({ tone })} data-tone={tone} data-digest={digest} role={tone === "failed" ? "alert" : "status"}>

            <p className="m-0 text-center text-ink">{message}</p>

            {action ?? null}

        </section>

    );

}
