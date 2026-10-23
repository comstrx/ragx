import { classes, variants } from "engine/style";
import { bench, do_not_optimize, measured } from "engine/tooling";

const look = variants("inline-flex items-center rounded-control-md border font-medium", {
    tone: { primary: "bg-primary text-onprimary", ghost: "bg-transparent text-ink", danger: "bg-danger text-onprimary" },
    size: { sm: "h-control-sm px-3", md: "h-control-md px-4", lg: "h-control-lg px-5", xl: "h-control-xl px-6" },
    width: { auto: "", full: "w-full" },
}, { tone: "primary", size: "md", width: "auto" });
const tones = ["primary", "ghost", "danger"] as const;
const sizes = ["sm", "md", "lg", "xl"] as const;

let turn = 0;

bench("variants, a known combination", () => do_not_optimize(look({ tone: "ghost", size: "lg" })));
bench("variants, rotating combinations", () => {

    turn += 1;
    do_not_optimize(look({ tone: tones[turn % 3] ?? "primary", size: sizes[turn % 4] ?? "md" }));

});
bench("classes, five parts", () => do_not_optimize(classes("a", false, "b c", null, "d")));

await measured({
    "variants, a known combination": 2,
    "variants, rotating combinations": 2,
    "classes, five parts": 2,
});
