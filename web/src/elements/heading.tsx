import { variants } from "@/lib/std/style";

type Level = 1 | 2 | 3;
type Tone = "default" | "eyebrow";
type Note = { text: string; tone?: "default" | "success" | "warning" };
type Props = { id?: string | undefined; level: Level; tone?: Tone; note?: Note | undefined; children: string };

const look = variants("m-0 text-balance text-ink", {
    level: {
        1: "text-2xl font-bold tracking-tight",
        2: "text-xl font-semibold tracking-tight",
        3: "text-lg font-semibold",
    },
    tone: {
        default: "",
        eyebrow: "text-sm font-semibold uppercase tracking-wide text-muted",
    },
}, { level: "1", tone: "default" });
const marked = variants("mt-2 block text-sm font-semibold uppercase tracking-wide", {
    tone: { default: "text-muted", success: "text-success", warning: "text-warning" },
}, { tone: "default" });

function Mark ({ note }: { note?: Note | undefined }) {

    if ( !note ) return null;

    return <small className={marked({ tone: note.tone ?? "default" })} data-tone={note.tone ?? "default"}>{note.text}</small>;

}
export default function Heading ({ id, level, tone = "default", note, children }: Props) {

    const className = look({ level: `${level}`, tone });

    if ( level === 1 ) return <h1 id={id} className={className} data-level="1">{children}<Mark note={note} /></h1>;
    if ( level === 2 ) return <h2 id={id} className={className} data-level="2">{children}<Mark note={note} /></h2>;

    return <h3 id={id} className={className} data-level="3">{children}<Mark note={note} /></h3>;

}
