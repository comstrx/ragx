type Props = { data: Record<string, unknown> };

function safe ( data: Record<string, unknown> ): string {

    return JSON.stringify(data).replaceAll("<", "\\u003c").replaceAll("\u2028", "\\u2028").replaceAll("\u2029", "\\u2029");

}
export default function Jsonld ({ data }: Props) {

    return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: safe(data) }} />;

}
