import { type Part, type Titled, titled } from "engine/screen";

export type Watched = Titled & { head: Node };

export function held ( target: Watched, parts: readonly Part[] ): () => void {

    const title = titled(target, parts);
    const keep = new MutationObserver(() => {

        if ( title && target.title !== title ) target.title = title;

    });

    keep.observe(target.head, { childList: true, subtree: true, characterData: true });

    return () => keep.disconnect();

}
