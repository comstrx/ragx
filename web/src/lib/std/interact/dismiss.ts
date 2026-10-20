import { type RefObject, useEffect } from "react";

export function useDismiss ( ref: RefObject<HTMLElement | null>, open: boolean, dismiss: () => void ): void {

    useEffect(() => {

        if ( !open ) return;

        const pressed = ( event: PointerEvent ): void => {

            if ( ref.current && event.target instanceof Node && !ref.current.contains(event.target) ) dismiss();

        };
        const typed = ( event: KeyboardEvent ): void => {

            if ( event.key === "Escape" ) dismiss();

        };

        document.addEventListener("pointerdown", pressed, true);
        document.addEventListener("keydown", typed);

        return () => {

            document.removeEventListener("pointerdown", pressed, true);
            document.removeEventListener("keydown", typed);

        };

    }, [ref, open, dismiss]);

}
