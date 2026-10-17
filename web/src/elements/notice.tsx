import Button from "@/elements/button";

type Props = {
    tone: "missing" | "failed" | "offline";
    message: string;
    action?: string | undefined;
    onAction?: (() => void) | undefined;
    digest?: string | undefined;
};

export default function Notice ({ tone, message, action, onAction, digest }: Props) {

    return (

        <section className="notice" data-tone={tone} data-digest={digest} role={tone === "failed" ? "alert" : "status"}>

            <p className="notice-message">{message}</p>

            {action && onAction ? <Button tone="ghost" size="sm" onClick={onAction}>{action}</Button> : null}

        </section>

    );

}
