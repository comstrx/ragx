import { permissionsOf } from "engine/client";
import { type ReactNode, Suspense } from "react";
import Pending from "@/elements/pending";
import Shell from "@/elements/shell";
import type { Screen as Facing, Route } from "@/lib/spec/feature";
import type { Locale } from "@/lib/spec/languages";
import { shellAt, text } from "@/lib/spec/runtime";
import type { Shell as Parts } from "@/lib/spec/surface";
import { Blocks, type Facts, placed } from "./blocks.tsx";
import { Boundary } from "./boundary.tsx";
import { ClientOnly } from "./client-only.ts";
import { Gate } from "./gate.ts";
import { Preload } from "./mount.ts";

type Props = { screen: Facing; route: Route };

const parts = ["nav", "sidebar", "footer", "loader"] as const;

async function part ( name: keyof Parts, screen: Facing, route: Route ): Promise<ReactNode> {

    const placement = shellAt(screen, name, route.locale as Locale);

    if ( !placement ) return null;

    return <Suspense>{await placed(placement.feature, { options: placement.options, ports: {}, screen, route })}</Suspense>;

}
export async function Screen ({ screen, route }: Props) {

    const locale = route.locale as Locale;
    const [nav, sidebar, footer, chosen] = await Promise.all(parts.map(( name ) => part(name, screen, route)));
    const loader = chosen ?? (screen.options.loader ? <Pending label={text({ key: "state.loading" }, locale)} /> : null);
    const facts: Facts = { screen, route, loader };

    const blocks = (

        <Boundary name={screen.name} message={text({ key: "state.failed" }, locale)} retry={text({ key: "state.retry" }, locale)}>

            <Suspense fallback={loader}><Blocks blocks={screen.blocks} facts={facts} /></Suspense>

        </Boundary>

    );

    const body = screen.client ? <ClientOnly fallback={loader}>{blocks}</ClientOnly> : blocks;
    const gated = screen.access === "any"
        ? body
        : <Gate access={permissionsOf(screen.access)} guest={screen.access === "guest"} redirect={screen.redirect}>{body}</Gate>;

    return (

        <Shell skip={text({ key: "nav.skip" }, locale)} page={screen.name} nav={nav} sidebar={sidebar} footer={footer}>

            {gated}

            <Preload />

        </Shell>

    );

}
