export type Part = string | false | null | undefined;
export type Axes = Readonly<Record<string, Readonly<Record<string, string>>>>;
export type Picked<A extends Axes> = { [K in keyof A]: `${Extract<keyof A[K], string | number>}` };
export type Look<A extends Axes> = ( chosen?: Partial<Picked<A>> ) => string;

export function classes ( ...parts: readonly Part[] ): string {

    return parts.filter(( part ): part is string => typeof part === "string" && part.length > 0).join(" ");

}
export function variants<const A extends Axes> ( base: string, axes: A, defaults: Picked<A> ): Look<A> {

    const names = Object.keys(axes) as (keyof A & string)[];
    const known = new Map<string, string>();

    return ( chosen = {} ) => {

        const picked = names.map(( name ) => chosen[name] ?? defaults[name]);
        const key = picked.join("\u0000");
        const found = known.get(key);

        if ( found !== undefined ) return found;

        const value = classes(base, ...names.map(( name, index ) => axes[name]?.[picked[index] ?? ""]));

        known.set(key, value);

        return value;

    };

}
