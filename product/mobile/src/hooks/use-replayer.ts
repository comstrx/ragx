import { useReplay } from "@/hooks/use-client";
import { useDevice } from "@/hooks/use-device";

export function useReplayer (): void {

    useReplay(useDevice());

}
