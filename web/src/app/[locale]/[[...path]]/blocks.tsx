import registry from "@spec/registry";
import { createElement, Fragment, type ReactNode, Suspense } from "react";
import Block from "@/elements/block";
import type { FeatureProps, Route, Screen } from "@/lib/spec/feature";
import type { CompiledWebBlock as CompiledBlock, CompiledWebFeature as CompiledFeature } from "@/lib/spec/surface";
import { placementOf } from "@/lib/std/screen";
import { Boundary } from "./boundary.tsx";
import { Gate } from "./gate.ts";
import { Mount } from "./mount.ts";

export type Facts = { screen: Screen; route: Route; loader: ReactNode };

export async function placed ( name: string, props: FeatureProps ): Promise<ReactNode> {

    const load = registry[name];

    if ( !load ) return <Mount name={name} {...props} />;

    return createElement((await load()).default, props);

}
async function One ({ entry, facts }: { entry: CompiledFeature; facts: Facts }) {

    const held = entry.features.length + entry.blocks.length > 0;
    const children = held ? (

        <Fragment>

            <Features entries={entry.features} facts={facts} />

            <Blocks blocks={entry.blocks} facts={facts} />

        </Fragment>

    ) : undefined;

    const { screen, route } = facts;

    return placed(entry.name, { options: entry.options, ports: entry.ports, screen, route, feature: placementOf(entry), children });

}
function Placed ({ entry, facts }: { entry: CompiledFeature; facts: Facts }) {

    const one = <One entry={entry} facts={facts} />;
    const blocking = entry.heading && entry.owner === "server";
    const view = <Boundary name={entry.id}>{blocking ? one : <Suspense fallback={facts.loader}>{one}</Suspense>}</Boundary>;

    return entry.access.length ? <Gate access={entry.access}>{view}</Gate> : view;

}
function Features ({ entries, facts }: { entries: readonly CompiledFeature[]; facts: Facts }) {

    return entries.map(( entry ) => <Placed key={entry.id} entry={entry} facts={facts} />);

}
export function Blocks ({ blocks, facts }: { blocks: readonly CompiledBlock[]; facts: Facts }) {

    return blocks.map(( block ) => {

        const features = block.features.map(( entry ) => ({ id: entry.id, node: <Placed entry={entry} facts={facts} /> }));
        const children = block.blocks.map(( child ) => ({ id: child.id, node: <Blocks blocks={[child]} facts={facts} /> }));

        return <Block key={block.id} {...block.options} entries={[...features, ...children]} />;

    });

}
