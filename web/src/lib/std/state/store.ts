import { createStore as createZustand, type StoreApi } from "zustand/vanilla";
import { pick } from "@/lib/std/base";
import { type Store as Persistence, typed } from "@/lib/std/storage";

export type Setter<S> = ( patch: Partial<S> | (( state: S ) => Partial<S>) ) => void;
export type Getter<S> = () => S;
export type Actions<S, A> = ( set: Setter<S>, get: Getter<S> ) => A;
export type Persist<S> = {
    store: Persistence;
    keys?: readonly (keyof S & string)[] | undefined;
    version?: number | undefined;
    fields?: boolean | undefined;
    parse?: (( saved: unknown ) => Partial<S> | undefined) | undefined;
};
export type Definition<S extends object, A extends object> = {
    name: string;
    initial: S;
    actions: Actions<S, A>;
    persist?: Persist<S> | undefined;
};
export type Status = { ready: boolean };
export type State<S, A> = S & A & Status;
export type Instance<S extends object, A extends object> = StoreApi<State<S, A>> & {
    hydrate: () => Promise<void>;
    reset: () => void;
};
export type Defined<S extends object, A extends object> = {
    name: string;
    create: () => Instance<S, A>;
};

type Saved<S> = { version: number; state: Partial<S> };
type Keeper<S> = { read: () => Promise<Partial<S> | undefined>; write: ( state: Partial<S> ) => Promise<void> };

function whole<S> ( store: Persistence, name: string, version: number ): Keeper<S> {

    const saved = typed<Saved<S>>(store);

    return {
        read: async () => {

            const found = await saved.read(name);

            return found && found.version === version ? found.state : undefined;

        },
        write: ( state ) => saved.write(name, { version, state }),
    };

}
function fields<S> ( store: Persistence, keys: readonly (keyof S & string)[], initial: S ): Keeper<S> {

    const present = keys.filter(( key ) => initial[key] !== undefined && initial[key] !== null);
    const written = new Map(present.map(( key ) => [key, String(initial[key])] as const));

    return {
        read: async () => {

            const found = await Promise.all(keys.map(async ( key ) => [key, await store.get(key)] as const));

            const present = found.filter(( entry ): entry is readonly [keyof S & string, string] => entry[1] !== null);

            for ( const [key, value] of present ) written.set(key, value);

            return Object.fromEntries(present) as Partial<S>;

        },
        write: async ( state ) => {

            for ( const key of keys ) {

                const value = state[key];
                const text = value === undefined || value === null ? undefined : String(value);

                if ( text === undefined || written.get(key) === text ) continue;

                written.set(key, text);

                await store.set(key, text);

            }

        },
    };

}
export function defineStore<S extends object, A extends object> ( definition: Definition<S, A> ): Defined<S, A> {

    const { name, initial, actions, persist } = definition;
    const version = persist?.version ?? 1;

    return {
        name,
        create: () => {

            const store = createZustand<State<S, A>>(( set, get ) => {

                const setter: Setter<S> = ( patch ) => {

                    set(( state ) => (typeof patch === "function" ? patch(state) : patch) as Partial<State<S, A>>);

                };
                const getter: Getter<S> = () => get();

                return { ...initial, ready: !persist, ...actions(setter, getter) };

            });
            const keys = persist?.keys ?? (Object.keys(initial) as (keyof S & string)[]);
            const saved = persist && (persist.fields ? fields<S>(persist.store, keys, initial) : whole<S>(persist.store, name, version));
            let writing = false;
            let queued: Partial<S> | undefined;
            const flush = (): void => {

                if ( writing || !queued || !saved ) return;

                const next = queued;

                queued = undefined;
                writing = true;
                void saved
                    .write(next)
                    .catch(() => undefined)
                    .finally(() => {

                        writing = false;
                        flush();

                    });

            };

            if ( saved ) {

                store.subscribe(( state ) => {

                    if ( !state.ready ) return;

                    queued = pick(state, keys) as Partial<S>;
                    flush();

                });

            }

            return Object.assign(store, {
                hydrate: async () => {

                    if ( persist && saved ) {

                        const state = await saved.read().catch(() => undefined);
                        const accepted = state && persist.parse ? persist.parse(state) : state;

                        if ( accepted ) store.setState(accepted as Partial<State<S, A>>);

                    }

                    store.setState({ ready: true } as Partial<State<S, A>>);

                },
                reset: () => {

                    store.setState({ ...initial, ready: true } as Partial<State<S, A>>);

                },
            });

        },
    };

}
