import { describe, expect, test } from "bun:test";
import { analyze, type Rules } from "engine/tooling";

const rules: Rules = {
    source: "/part/src",
    specs: "/part/specs",
    foundation: /^(react(?:\/|$)|engine\/)/,
    native: /^react-native(?:\/|$)/,
    free: ["elements/", "hooks/"], vendor: ["lib/providers/"],
    html: true,
    markupFiles: /^(?:elements|components)\/[^/]+$|^features\/[^/]+\/(?:index|components\/[^/]+)$/,
    hookFiles: /^hooks\//,
    featureEntry: /^features\/([^/]+)\/index\.tsx$/,
    featureComponent: /^features\/([^/]+)\/components\//,
    extensions: ["", ".ts", ".tsx"],
    helpers: ["screen", "block", "feature", "t"],
    structure: ["api", "elements", "components", "features", "hooks", "lib"],
    flat: ["elements", "hooks"],
    markup: ["elements"],
    featureParts: ["index.tsx", "components"],
    apiParts: ["features", "workflow"],
    owners: {},
    declarations: [],
    layer: () => 0,
};

describe("architecture", () => {

    test("markup, styling and native primitives are refused outside elements", () => {

        const { issues } = analyze(
            "components/card.tsx",
            'import { View } from "react-native";\nexport default function Card () { return <View className="x"><section /></View>; }',
            rules,
        );

        expect(issues).toEqual([
            "Native primitives belong in elements: react-native",
            "HTML belongs in elements: section",
            "Styling belongs in elements: className",
        ]);

    });
    test("a feature entry stays thin and declares its owner", () => {

        const { issues } = analyze(
            "features/cards/index.tsx",
            'import Card from "@/elements/card";\nexport default function Cards () { return <Card />; }',
            rules,
            "server",
        );

        expect(issues).toEqual([
            "A feature entry is thin: it imports its own components only, not @/elements/card",
            "Feature entries declare client or server ownership.",
        ]);

    });
    test("specs are data", () => {

        const { issues } = analyze(
            "../specs/site/schema/home.ts",
            'import { screen } from "@/lib/spec/surface";\nexport default screen({ a: compute(1) });',
            rules,
        );

        expect(issues).toEqual(["Specs may call typed definition helpers only: compute"]);

    });
    test("an element stands alone: no other element, no hook, no store, no style or attribute bag in its props", () => {

        const leafy: Rules = { ...rules, markup: ["elements", "icons"] };
        const of = ( path: string, code: string ) => analyze(path, code, leafy).issues;
        const lone = "An element stands alone: it imports icons, styles, engine, lib/providers and types only, not";
        const semantic = "Elements take semantic props only: className, style and HTML attribute bags are refused.";
        const markup = "\nexport default function N () { return <p />; }";
        const bagged = 'import type { ComponentProps } from "react";\nexport default function C ( p: ComponentProps<"p"> ) { return <p />; }';
        const lawful = `import { variants } from "engine/style";\nimport Mark from "@/icons/mark";${markup}`;

        expect(of("elements/notice.tsx", `import Button from "@/elements/button";${markup}`)).toEqual([`${lone} @/elements/button`]);
        expect(of("elements/notice.tsx", `import B from "./button.tsx";${markup}`)).toEqual([`${lone} ./button.tsx`]);
        expect(of("elements/card.tsx", `import { useApi } from "@/hooks/use-client";${markup}`)).toEqual([`${lone} @/hooks/use-client`]);
        expect(of("elements/card.tsx", `type P = { className?: string };${markup}`)).toEqual([semantic]);
        expect(of("elements/card.tsx", bagged)).toEqual([semantic]);
        expect(of("elements/card.tsx", lawful)).toEqual([]);
        expect(of("icons/mark.tsx", `import Button from "@/elements/button";${markup}`)).toEqual([
            "An icon stands alone: it imports styles, engine and types only, not @/elements/button",
        ]);

    });
    test("a component composes elements, icons, components and its own hook only", () => {

        const of = ( code: string ) => analyze("components/table-pagination.tsx", code, rules).issues;
        const only = "A component composes elements, icons, components and its own hook hooks/use-table-pagination only, not";

        const body = "\nexport default function T () { return null; }";
        const composed = 'import Button from "@/elements/button";\nimport Pager from "@/components/pager";';
        const owned = 'import { usePager } from "@/hooks/use-table-pagination";';

        expect(of(composed + body)).toEqual([]);
        expect(of(owned + body)).toEqual([]);
        expect(of(`import { useApi } from "@/hooks/use-client";${body}`)).toEqual([`${only} @/hooks/use-client`]);
        expect(of(`import { unique } from "engine/array";${body}`)).toEqual([`${only} engine/array`]);
        expect(of(`import { store } from "@/stores/table";${body}`)).toEqual([`${only} @/stores/table`]);

    });

});
describe("spec isolation", () => {

    test("a spec may import its own modules and the surface door only, never another spec or src", () => {

        const own = analyze(
            "../specs/site/schema/home.ts",
            'import x from "./parts/x.ts";\nimport { screen } from "@/lib/spec/surface";\nexport default screen(x);',
            rules,
        );
        const other = analyze(
            "../specs/site/schema/home.ts",
            'import y from "../../other/schema/home.ts";\nexport default y;',
            rules,
        );
        const deep = analyze(
            "../specs/site/schema/home.ts",
            'import { config } from "../../../src/lib/spec/server.ts";\nexport default config;',
            rules,
        );
        const relative = analyze(
            "../specs/site/schema/home.ts",
            'import { screen } from "../../../src/lib/spec/surface.ts";\nexport default screen();',
            rules,
        );

        expect(own.issues).toEqual([]);
        expect(other.issues).toEqual(["Specs import their own modules and @/lib/spec/surface only."]);
        expect(deep.issues).toEqual(["Specs import their own modules and @/lib/spec/surface only."]);
        expect(relative.issues).toEqual(["Specs import their own modules and @/lib/spec/surface only."]);

    });
    test("a spec behind (group) folders is its own home; a sibling in the same group is another spec", () => {

        const own = analyze(
            "../specs/(saasx)/(v1)/admin/schema/home.ts",
            'import x from "../config/parts.ts";\nexport default x;',
            rules,
        );
        const sibling = analyze(
            "../specs/(saasx)/(v1)/admin/schema/home.ts",
            'import y from "../../client/schema/home.ts";\nexport default y;',
            rules,
        );

        expect(own.issues).toEqual([]);
        expect(sibling.issues).toEqual(["Specs import their own modules and @/lib/spec/surface only."]);

    });

});
