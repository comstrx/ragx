import Heading from "@/elements/heading";

type Props = { id: string; message: string; note: string; tone: "default" | "success" | "warning"; primary: boolean };

export default function Greeting ({ id, message, note, tone, primary }: Props) {

    return <Heading id={id} level={primary ? 1 : 2} note={{ text: note, tone }}>{message}</Heading>;

}
