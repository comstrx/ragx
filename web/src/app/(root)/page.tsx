import type { Route } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { build, routing } from "@/lib/spec/config";
import { choose } from "@/lib/std/base";
import { negotiate } from "@/lib/std/translate";
import { Entry } from "./entry.ts";

export default async function Root () {

    if ( build.output !== "standalone" ) return <Entry />;

    const preferred = negotiate((await headers()).get("accept-language"), routing.locales);

    redirect(`/${choose(routing.locales, preferred, routing.defaultLocale)}` as Route);

}
