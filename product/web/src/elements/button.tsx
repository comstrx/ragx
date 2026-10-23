import { variants } from "engine/style";

type Props = {
    tone?: "primary" | "ghost" | "danger";
    size?: "sm" | "md" | "lg" | "xl";
    width?: "auto" | "full";
    type?: "button" | "submit";
    disabled?: boolean;
    onClick?: () => void;
    children: string;
};

const look = variants(
    [
        "inline-flex cursor-pointer select-none items-center justify-center gap-2 rounded-control-md border font-medium",
        "transition-[background-color,border-color,color,box-shadow,translate] duration-(--motion-fast) ease-standard",
        "enabled:active:translate-y-px disabled:cursor-not-allowed disabled:opacity-(--dim-disabled)",
    ].join(" "),
    {
        tone: {
            primary: "border-primary bg-primary text-onprimary shadow-control enabled:hover:brightness-105",
            ghost: "border-line bg-transparent text-ink enabled:hover:bg-hover enabled:active:bg-press",
            danger: "border-danger bg-danger text-onprimary shadow-control enabled:hover:brightness-105",
        },
        size: {
            sm: "h-control-sm px-3 text-sm",
            md: "h-control-md px-4 text-md",
            lg: "h-control-lg px-5 text-md",
            xl: "h-control-xl px-6 text-lg",
        },
        width: { auto: "", full: "w-full" },
    },
    { tone: "primary", size: "md", width: "auto" },
);

export default function Button ({ tone = "primary", size = "md", width = "auto", type = "button", disabled = false, onClick, children }: Props) {

    return (

        <button type={type} className={look({ tone, size, width })} data-tone={tone} data-size={size} disabled={disabled} onClick={onClick}>

            {children}

        </button>

    );

}
