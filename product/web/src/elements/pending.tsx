type Props = { label: string };

export default function Pending ({ label }: Props) {

    return (

        <div role="status" aria-live="polite" className="grid min-h-96 animate-reveal place-items-center">

            <span aria-hidden="true" className="size-glyph-xl animate-spin rounded-full border-2 border-line border-t-primary" />

            <span className="sr-only">{label}</span>

        </div>

    );

}
