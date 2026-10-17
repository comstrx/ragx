import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Jsonld from "@/elements/jsonld";
import { pageMetadata, structuredData } from "@/lib/seo";
import { build } from "@/lib/spec/config";
import type { Locale } from "@/lib/spec/languages";
import { localize, type Matched, paths, routing, screenAt } from "@/lib/spec/runtime";
import { choose } from "@/lib/std/base";
import { Screen } from "./screen.tsx";

type Query = Record<string, string | string[] | undefined>;
type Params = { locale: string; path?: string[] };
type Props = { params: Promise<Params>; searchParams: Promise<Query> };
type Found = { locale: Locale; matched: Matched };

export function generateStaticParams (): { path: string[] }[] {

    return paths.map(( path ) => ({ path: path.split("/").filter(Boolean) }));

}
function found ( params: Params ): Found {

    const locale = choose(routing.locales, params.locale, routing.defaultLocale);
    const matched = screenAt(params.path ?? []);

    if ( !matched ) notFound();

    return { locale, matched };

}
export async function generateMetadata ({ params }: Props): Promise<Metadata> {

    const { locale, matched } = found(await params);

    return pageMetadata(matched, locale);

}
export default async function Page ({ params, searchParams }: Props) {

    const { locale, matched } = found(await params);
    const query = build.output === "standalone" ? await searchParams : {};
    const screen = localize({ ...matched, parameters: {} }, locale);
    const graph = structuredData(matched, locale);

    return (

        <>

            {graph ? <Jsonld data={graph} /> : null}

            <Screen screen={screen} route={{ locale, parameters: matched.parameters, query }} />

        </>

    );

}
