import process from "node:process";
import { $ } from "bun";
import { report, task } from "engine/tooling";
import { installedSpecs, specFromEnvironment } from "./core.ts";

export async function deliverSpecs ( every: boolean ): Promise<string[]> {

    const specs = every ? installedSpecs() : [specFromEnvironment()];

    for ( const spec of specs ) {

        const env = { ...process.env, NEXT_PUBLIC_SPEC: spec };

        report(`deliver ${spec}`);
        await $`bun tools/compile.ts production`.env(env);
        await $`bunx next build`.env(env);
        await $`bun tools/audit.ts`.env(env);

    }

    return specs;

}

task(import.meta.url, async () => {

    await deliverSpecs(process.argv.includes("--all"));

});
