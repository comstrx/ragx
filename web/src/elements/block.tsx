import type { CSSProperties, ReactNode } from "react";
import type { BlockOptions } from "@/lib/spec/surface";
import { classes, variants } from "@/lib/std/style";

type Entry = { id: string; node: ReactNode };
type Props = BlockOptions & { entries: readonly Entry[] };
type Point = "base" | "sm" | "md" | "lg" | "xl";

const columns: Record<Point, readonly string[]> = {
    base: ["grid-cols-1", "grid-cols-2", "grid-cols-3", "grid-cols-4", "grid-cols-5", "grid-cols-6"],
    sm: ["sm:grid-cols-1", "sm:grid-cols-2", "sm:grid-cols-3", "sm:grid-cols-4", "sm:grid-cols-5", "sm:grid-cols-6"],
    md: ["md:grid-cols-1", "md:grid-cols-2", "md:grid-cols-3", "md:grid-cols-4", "md:grid-cols-5", "md:grid-cols-6"],
    lg: ["lg:grid-cols-1", "lg:grid-cols-2", "lg:grid-cols-3", "lg:grid-cols-4", "lg:grid-cols-5", "lg:grid-cols-6"],
    xl: ["xl:grid-cols-1", "xl:grid-cols-2", "xl:grid-cols-3", "xl:grid-cols-4", "xl:grid-cols-5", "xl:grid-cols-6"],
};
const section = variants("min-w-0", {
    width: {
        auto: "",
        full: "w-full",
        half: "w-full lg:w-1/2",
        third: "w-full lg:w-1/3",
        "two-thirds": "w-full lg:w-2/3",
        quarter: "w-full lg:w-1/4",
        narrow: "mx-auto w-full max-w-narrow",
        wide: "mx-auto w-full max-w-wide",
    },
    height: { auto: "", screen: "grid min-h-screen" },
    tone: {
        default: "",
        surface: "border border-line bg-panel",
        primary: "bg-primary text-onprimary",
        inverse: "bg-ink text-body",
    },
    radius: { none: "", sm: "rounded-panel-sm", md: "rounded-panel-md", lg: "rounded-panel-lg", xl: "rounded-panel-xl" },
    shadow: { none: "", sm: "shadow-panel-sm", md: "shadow-panel-md", lg: "shadow-panel-lg" },
    padding: { 0: "", 1: "p-1", 2: "p-2", 3: "p-3", 4: "p-4", 6: "p-6", 8: "p-8", 12: "p-12" },
}, { width: "full", height: "auto", tone: "default", radius: "none", shadow: "none", padding: "0" });
const flow = variants("min-w-0", {
    mode: { grid: "grid", row: "flex flex-col lg:flex-row" },
    gap: { 0: "gap-0", 1: "gap-1", 2: "gap-2", 3: "gap-3", 4: "gap-4", 6: "gap-6", 8: "gap-8", 12: "gap-12" },
    align: {
        start: "items-start justify-items-start",
        center: "place-items-center content-center justify-center",
        end: "items-end justify-items-end",
        stretch: "items-stretch",
    },
}, { mode: "grid", gap: "6", align: "stretch" });
const cell = "min-w-0 flex-(--cell-size)";

function grid ( chosen: BlockOptions["grid"] ): string {

    const counts: Partial<Record<Point, number>> = typeof chosen === "number" ? { base: chosen } : chosen;

    return classes(...(Object.keys(columns) as Point[]).map(( point ) => columns[point][(counts[point] ?? 0) - 1]));

}
function share ( size: number ): CSSProperties {

    return { "--cell-size": String(size) } as CSSProperties;

}
export default function Block ({ entries, grid: counts, sizes, gap, padding, align, width, height, tone, radius, shadow }: Props) {

    const sized = sizes.length > 0;
    const mode = sized ? "row" : "grid";

    return (

        <section
            className={section({ width, height, tone, radius, shadow, padding: `${padding}` })}
            data-width={width}
            data-height={height}
            data-tone={tone}
        >

            <div className={classes(flow({ mode, gap: `${gap}`, align }), sized ? "" : grid(counts))} data-mode={mode}>

                {entries.map(( entry, index ) => (

                    <div key={entry.id} className={sized ? cell : "min-w-0"} style={sized ? share(sizes[index] ?? 1) : undefined}>

                        {entry.node}

                    </div>

                ))}

            </div>

        </section>

    );

}
