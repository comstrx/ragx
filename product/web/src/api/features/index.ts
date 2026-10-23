import { document, type Endpoint } from "engine/api";
import { contract, transportsOf, viewsOf } from "engine/spec";
import hello from "./hello.ts";

type Entity = { parameter: string; list?: string };

export const contracts = { site: contract({ transport: document("content") }), hello } as const;
export const endpoints = transportsOf(contracts);
export const views = viewsOf(contracts);
export const entities = {} as const satisfies Record<string, Entity>;

export type Endpoints = typeof endpoints;
export type Feature = keyof Endpoints & string;
export type OperationOf<F extends Feature> = keyof Endpoints[F] & string;
export type EndpointOf<F extends Feature, O extends OperationOf<F>> = Endpoints[F][O] extends Endpoint ? Endpoints[F][O] : never;
export type Operation = { [F in Feature]: `${F}.${OperationOf<F>}` }[Feature];
export type EntityKind = keyof typeof entities & string;
