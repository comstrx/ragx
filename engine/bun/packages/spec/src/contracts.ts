import type { Endpoint } from "engine/api";
import type { ManifestInput } from "./shapes.ts";

export type Transport = Readonly<Record<string, Endpoint>>;
export type Contract = { transport?: Transport | undefined; view?: ManifestInput | undefined };
export type Transports<C extends Readonly<Record<string, Contract>>> = {
    [K in keyof C as C[K] extends { transport: Transport } ? K : never]: C[K] extends { transport: infer T } ? T : never;
};
export type Views<C extends Readonly<Record<string, Contract>>> = {
    [K in keyof C as C[K] extends { view: ManifestInput } ? K : never]: C[K] extends { view: infer V } ? V : never;
};

export function contract<const C extends Contract> ( parts: C ): C {

    if ( !parts.transport && !parts.view ) throw new Error("A feature contract declares a transport, a view or both.");

    return parts;

}
export function transportsOf<const C extends Readonly<Record<string, Contract>>> ( contracts: C ): Transports<C> {

    const found = Object.entries(contracts).flatMap(( [name, { transport }] ) => (transport ? [[name, transport] as const] : []));

    return Object.fromEntries(found) as Transports<C>;

}
export function viewsOf<const C extends Readonly<Record<string, Contract>>> ( contracts: C ): Views<C> {

    const found = Object.entries(contracts).flatMap(( [name, { view }] ) => (view ? [[name, view] as const] : []));

    return Object.fromEntries(found) as Views<C>;

}
