import { StyleSheet, Text, View } from "react-native";
import { useFont } from "@/styles/font";
import { usePalette } from "@/styles/palette";

type Level = 1 | 2 | 3;
type Tone = "default" | "eyebrow";
type Note = { text: string; tone?: "default" | "success" | "warning" };
type Props = { id?: string | undefined; level: Level; tone?: Tone; note?: Note | undefined; children: string };

const styles = StyleSheet.create({
    heading: { fontWeight: "700", letterSpacing: -0.2 },
    one: { fontSize: 26, lineHeight: 32 },
    two: { fontSize: 21, lineHeight: 27 },
    three: { fontSize: 17, lineHeight: 23, fontWeight: "600" },
    eyebrow: { fontSize: 13, lineHeight: 18, fontWeight: "600", letterSpacing: 0.6, textTransform: "uppercase" },
    note: { marginTop: 8, fontSize: 13, lineHeight: 18, fontWeight: "600", letterSpacing: 0.6, textTransform: "uppercase" },
});
const sizes = { 1: styles.one, 2: styles.two, 3: styles.three } as const;
const notes = { default: "muted", success: "success", warning: "warning" } as const;

export default function Heading ({ id, level, tone = "default", note, children }: Props) {

    const palette = usePalette();
    const font = useFont();
    const shape = tone === "eyebrow" ? styles.eyebrow : sizes[level];
    const color = tone === "eyebrow" ? palette.muted : palette.ink;

    return (

        <View nativeID={id}>

            <Text role="heading" aria-level={level} style={[font, styles.heading, shape, { color }]}>{children}</Text>

            {note ? <Text style={[font, styles.note, { color: palette[notes[note.tone ?? "default"]] }]}>{note.text}</Text> : null}

        </View>

    );

}
