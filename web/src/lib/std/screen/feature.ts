import type { CompiledFeature, CompiledPort } from "@/lib/std/spec";

export type Route = {
    locale?: string | undefined;
    parameters: Record<string, string>;
    query: Record<string, string | string[] | undefined>;
    signals?: Record<string, unknown> | undefined;
};
export type Placement = { id: string; slug: string; heading: boolean; access: string[] };
export type FeatureProps<O, S, N> = {
    options: O;
    ports: Record<string, CompiledPort>;
    screen: S;
    route: Route;
    feature?: Placement | undefined;
    children?: N | undefined;
};

export function placementOf ( feature: CompiledFeature<object> ): Placement {

    return { id: feature.id, slug: feature.slug, heading: feature.heading, access: feature.access };

}
