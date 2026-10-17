type Tone = "default" | "eyebrow";
type Note = { text: string; tone?: "default" | "success" | "warning" };
type Props = { id?: string; level: 1 | 2 | 3; tone?: Tone; note?: Note; children: string };

function Mark ({ note }: { note?: Note | undefined }) {

    if ( !note ) return null;

    return <small className="heading-note" data-tone={note.tone ?? "default"}>{note.text}</small>;

}
export default function Heading ({ id, level, tone = "default", note, children }: Props) {

    if ( level === 1 ) {

        return <h1 id={id} className="heading" data-level="1" data-tone={tone}>{children}<Mark note={note} /></h1>;

    }

    if ( level === 2 ) {

        return <h2 id={id} className="heading" data-level="2" data-tone={tone}>{children}<Mark note={note} /></h2>;

    }

    return <h3 id={id} className="heading" data-level="3" data-tone={tone}>{children}<Mark note={note} /></h3>;

}
