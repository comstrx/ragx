export const themeDefaults = {
    colors: {
        light: {
            body: "#f6f7f8", panel: "#ffffff", raised: "#ffffff", sunken: "#eef0f2", ink: "#17191c", muted: "#656c75",
            line: "#e3e6ea", strong: "#c9ced5", focus: "#0aa38a", primary: "#0aa38a", onprimary: "#ffffff", accent: "#ff4500",
            success: "#0b7a49", warning: "#8a5300", danger: "#b0292f", info: "#1f5fb3",
        },
        dark: {
            body: "#0b0d10", panel: "#13161a", raised: "#1a1e24", sunken: "#07090b", ink: "#eceef1", muted: "#9aa3ad",
            line: "#22272e", strong: "#333a43", focus: "#2fd0b3", primary: "#2fd0b3", onprimary: "#06201b", accent: "#ff7a45",
            success: "#4cc38a", warning: "#f0b44c", danger: "#ff8a8f", info: "#7fb0ff",
        },
    },
};
export const space = { 0: 0, 1: 4, 2: 8, 3: 12, 4: 16, 6: 24, 8: 32, 12: 48 } as const;
export const radius = { none: 0, sm: 6, md: 12, lg: 20, full: 9999 } as const;
export const type = {
    xs: { size: 12, line: 16, weight: 400 },
    sm: { size: 14, line: 20, weight: 400 },
    md: { size: 16, line: 24, weight: 400 },
    lg: { size: 20, line: 28, weight: 600 },
    xl: { size: 28, line: 36, weight: 700 },
} as const;
export const motion = {
    durations: { instant: 0, fast: 120, base: 200, slow: 320, expressive: 600 },
    easings: {
        standard: "cubic-bezier(0.2, 0, 0, 1)",
        enter: "cubic-bezier(0, 0, 0, 1)",
        exit: "cubic-bezier(0.3, 0, 1, 1)",
        spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
    },
};
export const currency = { default: "USD", enabled: ["USD"] };
export const countries = ["EG", "SA", "AE"];
