import { type NextRequest, NextResponse } from "next/server";
import { preferences, routing } from "@/lib/spec/config";
import { reserved } from "@/lib/spec/routes";
import { routable, routeOf } from "@/lib/std/translate";

const varying = "Accept-Language, Cookie";
const routed = "x-routed";

function varied ( response: NextResponse ): NextResponse {

    response.headers.set("Vary", varying);

    return response;

}
export function proxy ( request: NextRequest ): NextResponse {

    const path = request.nextUrl.pathname;

    if ( !routable(path, reserved) || request.headers.has(routed) ) return NextResponse.next();

    const language = request.cookies.get(preferences.keys.language)?.value;
    const way = routeOf({ path, language, accept: request.headers.get("accept-language") }, routing);

    if ( way.kind === "pass" ) return NextResponse.next();

    const target = request.nextUrl.clone();

    target.pathname = way.path;

    if ( way.kind === "redirect" ) return varied(NextResponse.redirect(target, way.status));

    const headers = new Headers(request.headers);

    headers.set(routed, way.locale);

    return varied(NextResponse.rewrite(target, { request: { headers } }));

}
export const config = { matcher: ["/((?!_next/).*)"] };
