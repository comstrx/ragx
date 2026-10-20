import { isPlain } from "@/lib/std/base";
import { type Manifest, manifestShape } from "@/lib/std/spec";

export type Features = Record<string, Manifest>;

function literal ( value: unknown, where: string ): void {

    if ( value === null ) throw new Error(`${where}: null defaults are not typed; give a real default.`);

    if ( Array.isArray(value) ) {

        value.forEach(( item, index ) => {

            literal(item, `${where}[${index}]`);

        });

    } else if ( isPlain(value) ) {

        for ( const [key, item] of Object.entries(value) ) literal(item, `${where}.${key}`);

    } else if ( !["string", "number", "boolean"].includes(typeof value) ) {

        throw new Error(`${where}: options are literal values only.`);

    }

}
function manifestOf ( name: string, view: unknown ): Manifest {

    const where = `api/features/${name}.ts view`;
    const parsed = manifestShape.safeParse(view);

    if ( !parsed.success ) {

        const issues = parsed.error.issues.map(( issue ) => `${issue.path.join(".") || "view"} ${issue.message}`);

        throw new Error(`${where}: ${issues.join("; ")}`);

    }

    literal(parsed.data.options, `${where} options`);

    return parsed.data;

}
export function viewFacts ( views: Readonly<Record<string, unknown>> ): Features {

    return Object.fromEntries(Object.keys(views).sort().map(( name ) => [name, manifestOf(name, views[name])]));

}
