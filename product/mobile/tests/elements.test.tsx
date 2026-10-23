import { describe, expect, test } from "bun:test";
import type { ReactNode } from "react";
import { renderToString } from "react-dom/server";
import { Text } from "react-native";
import Block from "@/elements/block";
import Heading from "@/elements/heading";
import Loading from "@/elements/loading";
import Notice from "@/elements/notice";
import { config } from "@/lib/spec/runtime";
import { PreferencesProvider } from "@/stores/preferences";
import { palette } from "@/styles/theme";

const scheme = config.settings.theme.default === "light" ? "light" : "dark";
const colors = palette(scheme);
const base = { grid: 1, gap: 4, padding: 4, align: "stretch", width: "full", height: "auto", tone: "default", radius: "none" } as const;

function render ( node: ReactNode ): string {

    return renderToString(<PreferencesProvider>{node}</PreferencesProvider>);

}
function rgba ( hex: string ): string {

    const [r, g, b] = [1, 3, 5].map(( at ) => Number.parseInt(hex.slice(at, at + 2), 16));

    return `rgba(${r},${g},${b},1.00)`;

}

describe("mobile elements", () => {

    test("a heading carries its level to assistive tech and paints the ink of the active scheme", () => {

        expect(scheme).not.toBe(config.settings.theme.default === "system" ? scheme : "unset");

        for ( const level of [1, 2, 3] as const ) {

            const html = render(<Heading id={`h${level}`} level={level}>Title</Heading>);

            expect(html).toContain(`<h${level} dir="auto" aria-level="${level}" role="heading"`);
            expect(html).toContain(`id="h${level}"`);
            expect(html).toContain(`color:${rgba(colors.ink ?? "")}`);
            expect(html).toContain(">Title</h");

        }

    });
    test("a heading note takes its tone's color and an eyebrow reads muted; no note renders nothing extra", () => {

        const live = render(<Heading level={2} note={{ text: "Live", tone: "success" }}>T</Heading>);
        const offline = render(<Heading level={2} note={{ text: "Offline", tone: "warning" }}>T</Heading>);

        expect(live).toContain(`color:${rgba(colors.success ?? "")}">Live`);
        expect(offline).toContain(`color:${rgba(colors.warning ?? "")}">Offline`);
        expect(render(<Heading level={2} note={{ text: "Plain" }}>T</Heading>)).toContain(`color:${rgba(colors.muted ?? "")}">Plain`);
        expect(render(<Heading level={1} tone="eyebrow">Kicker</Heading>)).toContain(`color:${rgba(colors.muted ?? "")}">Kicker`);
        expect(render(<Heading level={1}>Bare</Heading>).match(/dir="auto"/g)).toHaveLength(1);

    });
    test("a failed notice is an alert with its action; a missing one is plain text without a button", () => {

        const failed = render(<Notice tone="failed" message="Broken" action="Retry" onAction={() => undefined} palette={colors} />);
        const missing = render(<Notice tone="missing" message="Nowhere" palette={colors} />);
        const silent = render(<Notice tone="failed" message="Broken" action="Retry" palette={colors} />);

        expect(failed).toContain('role="alert"');
        expect(failed).toContain('role="button"');
        expect(failed).toContain(">Retry<");
        expect(missing).not.toContain('role="button"');
        expect(missing).toContain(">Nowhere<");
        expect(silent).not.toContain('role="button"');

    });
    test("a block lays its entries on the grid, caps a narrow width and draws the surface tone", () => {

        const entries = [{ id: "a", node: <Text>First</Text> }, { id: "b", node: <Text>Second</Text> }];
        const narrow = render(<Block {...base} width="narrow" grid={2} tone="surface" entries={entries} palette={colors} />);

        expect(narrow).toContain(">First<");
        expect(narrow).toContain(">Second<");
        expect(narrow).toContain("max-width:420px");
        expect(narrow).toContain("flex-basis:50%");
        expect(narrow).toContain(`background-color:${rgba(colors.panel ?? "")}`);
        expect(render(<Block {...base} entries={entries} palette={colors} />)).not.toContain("max-width");

    });
    test("the loader spins in the primary color", () => {

        const html = render(<Loading palette={colors} />);

        expect(html).toContain('role="progressbar"');
        expect(html).toContain(`stroke:${colors.primary}`);

    });

});
