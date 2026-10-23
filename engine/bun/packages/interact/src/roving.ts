import type { KeyboardEvent } from "react";

export type Axis = "horizontal" | "vertical";

const keys = {
    horizontal: { next: "ArrowRight", previous: "ArrowLeft" },
    vertical: { next: "ArrowDown", previous: "ArrowUp" },
} as const;

export function stepOf ( key: string, axis: Axis, rtl: boolean ): number | "first" | "last" | null {

    if ( key === "Home" ) return "first";
    if ( key === "End" ) return "last";

    const flip = axis === "horizontal" && rtl ? -1 : 1;

    if ( key === keys[axis].next ) return flip;
    if ( key === keys[axis].previous ) return -flip;

    return null;

}
export function indexOf ( current: number, step: number | "first" | "last", count: number ): number {

    if ( step === "first" ) return 0;
    if ( step === "last" ) return count - 1;
    if ( current < 0 ) return step > 0 ? 0 : count - 1;

    return (current + step + count) % count;

}
export function rove ( event: KeyboardEvent<HTMLElement>, axis: Axis, selector: string ): void {

    const items = [...event.currentTarget.querySelectorAll<HTMLElement>(selector)];
    const current = document.activeElement instanceof HTMLElement ? items.indexOf(document.activeElement) : -1;
    const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
    const step = stepOf(event.key, axis, rtl);

    if ( step === null || !items.length ) return;

    event.preventDefault();
    items[indexOf(current, step, items.length)]?.focus();

}
