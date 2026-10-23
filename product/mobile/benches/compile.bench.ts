import { catalogueFacts } from "engine/spec";
import { bench, identityOf, measured, viewFacts } from "engine/tooling";
import { endpoints, views } from "../src/api/features/index.ts";
import { validateSpec } from "../src/lib/spec/surface.ts";
import { composeMessages, installedSpecs, root } from "../tools/core.ts";

const facts = viewFacts(views);
const catalogue = catalogueFacts(endpoints);

for ( const path of installedSpecs() ) {

    const identity = identityOf(path);
    const folder = `${root}/specs/${path}`;
    const [config, schema] = (await Promise.all([
        import(`${folder}/config/index.ts`),
        import(`${folder}/schema/index.ts`),
    ])) as [{ default: unknown }, { default: unknown }];
    const messages = composeMessages(`${folder}/brand/messages`);

    bench(`compile the ${identity} spec`, () => validateSpec(identity, config.default, schema.default, messages, facts, catalogue));
    bench(`compose the ${identity} messages`, () => composeMessages(`${folder}/brand/messages`));

}

await measured({
    "compile the admin spec": 20000,
    "compose the admin messages": 3000,
    "compile the client spec": 20000,
    "compose the client messages": 3000,
});
