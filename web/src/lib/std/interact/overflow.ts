import { type RefObject, useEffect, useRef, useState } from "react";

export type Edges = { start: boolean; end: boolean };
export type Toward = "start" | "end";
export type Overflow<E extends HTMLElement> = Edges & { ref: RefObject<E | null>; scroll: ( toward: Toward ) => void };

const tolerance = 1;
const stride = 0.8;
const still: Edges = { start: false, end: false };

export function edgesOf ( offset: number, visible: number, total: number ): Edges {

    const distance = Math.abs(offset);

    return { start: distance > tolerance, end: distance + visible < total - tolerance };

}
export function strideOf ( toward: Toward, visible: number, rtl: boolean ): number {

    const sign = (toward === "end" ? 1 : -1) * (rtl ? -1 : 1);

    return Math.round(visible * stride) * sign;

}
export function useOverflow<E extends HTMLElement> (): Overflow<E> {

    const ref = useRef<E>(null);
    const [edges, setEdges] = useState<Edges>(still);

    useEffect(() => {

        const element = ref.current;

        if ( !element ) return;

        const measure = (): void => {

            const next = edgesOf(element.scrollLeft, element.clientWidth, element.scrollWidth);

            setEdges(( current ) => (current.start === next.start && current.end === next.end ? current : next));

        };
        const resized = new ResizeObserver(measure);
        const changed = new MutationObserver(measure);

        resized.observe(element);
        changed.observe(element, { childList: true, subtree: true, characterData: true });
        element.addEventListener("scroll", measure, { passive: true });
        measure();

        return () => {

            resized.disconnect();
            changed.disconnect();
            element.removeEventListener("scroll", measure);

        };

    }, []);

    const scroll = ( toward: Toward ): void => {

        const element = ref.current;

        if ( !element ) return;

        const rtl = getComputedStyle(element).direction === "rtl";
        const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;

        element.scrollBy({ left: strideOf(toward, element.clientWidth, rtl), behavior: calm ? "auto" : "smooth" });

    };

    return { ref, ...edges, scroll };

}
