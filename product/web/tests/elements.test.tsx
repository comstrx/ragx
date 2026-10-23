import { describe, expect, test } from "bun:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Block from "@/elements/block";
import Button from "@/elements/button";
import Heading from "@/elements/heading";
import Jsonld from "@/elements/jsonld";
import Notice from "@/elements/notice";
import Pending from "@/elements/pending";
import Shell from "@/elements/shell";

const html = ( node: ReactElement ): string => renderToStaticMarkup(node);
const layout = { width: "full", height: "auto", gap: 4, padding: 0, align: "stretch", tone: "default", radius: "none", shadow: "none" } as const;
const entries = [{ id: "a", node: "A" }, { id: "b", node: "B" }];

describe("elements", () => {

    test("a heading is one tag at its level, styled from the type scale, with an optional toned note inside it", () => {

        expect(html(<Heading id="t" level={1}>Title</Heading>)).toBe(
            '<h1 id="t" class="m-0 text-balance text-ink text-2xl font-bold tracking-tight" data-level="1">Title</h1>',
        );
        expect(html(<Heading level={3} tone="eyebrow">Sub</Heading>)).toContain('class="m-0 text-balance text-ink text-lg font-semibold text-sm');
        expect(html(<Heading level={2} note={{ text: "Live", tone: "success" }}>Hi</Heading>)).toContain(
            '<small class="mt-2 block text-sm font-semibold uppercase tracking-wide text-success" data-tone="success">Live</small></h2>',
        );

    });
    test("a button is never a submit by accident, sizes by the control scale and keeps its tone and state", () => {

        const plain = html(<Button onClick={() => undefined}>Go</Button>);
        const small = html(<Button type="submit" tone="danger" size="sm" disabled>Drop</Button>);
        const wide = html(<Button tone="ghost" size="xl" width="full">Wait</Button>);

        expect(plain).toStartWith('<button type="button" class="inline-flex');
        expect(plain).toContain("rounded-control-md");
        expect(plain).toContain("h-control-md px-4 text-md");
        expect(plain).toContain('data-tone="primary" data-size="md">Go</button>');
        expect(small).toContain('type="submit"');
        expect(small).toContain("border-danger bg-danger");
        expect(small).toContain("h-control-sm px-3 text-sm");
        expect(small).toContain(" disabled");
        expect(wide).toContain("h-control-xl px-6 text-lg w-full");
        expect(wide).toContain("enabled:hover:bg-hover enabled:active:bg-press");

    });
    test("a notice speaks as an alert only when something failed, and holds the action its caller composed", () => {

        const failed = html(<Notice tone="failed" message="Broke" action={<Button tone="ghost" size="sm">Retry</Button>} digest="d1" />);
        const missing = html(<Notice tone="missing" message="Gone" />);

        expect(failed).toContain('role="alert"');
        expect(failed).toContain('data-digest="d1"');
        expect(failed).toContain("border-danger-edge");
        expect(failed).toContain('data-tone="ghost" data-size="sm">Retry</button>');
        expect(missing).toContain('role="status"');
        expect(missing).toContain("border-line");
        expect(missing).not.toContain("<button");

    });
    test("the shell offers a hidden-until-focused skip link to the focusable main and renders only the parts it is given", () => {

        const bare = html(<Shell skip="Skip" page="home">Body</Shell>);
        const framed = html(<Shell skip="Skip" page="home" nav="N" sidebar="S" footer="F">Body</Shell>);

        expect(bare).toContain('<a href="#content" class="sr-only');
        expect(bare).toContain("focus:not-sr-only");
        expect(bare).toContain('<main id="content" tabindex="-1" class="min-w-0 flex-1 outline-none">Body</main>');
        expect(bare).not.toContain("<header");
        expect(bare).not.toContain("<aside");
        expect(framed).toContain('<header class="sticky top-0');
        expect(framed).toContain('data-sidebar=""><aside data-scroll="" class="overflow-y-auto');
        expect(framed).toContain('<footer class="border-t border-line bg-panel">F</footer>');

    });
    test("a block lays its entries on a responsive grid by default and shares one row by the declared sizes", () => {

        const grid = html(<Block {...layout} grid={{ base: 1, lg: 2 }} sizes={[]} entries={entries} />);
        const row = html(<Block {...layout} grid={1} sizes={[2, 1]} entries={entries} />);
        const dressed = { ...layout, tone: "surface", radius: "lg", shadow: "md", padding: 6, width: "narrow" } as const;
        const framed = html(<Block {...dressed} grid={3} sizes={[]} entries={entries} />);

        expect(grid).toContain('<div class="min-w-0 grid gap-4 items-stretch grid-cols-1 lg:grid-cols-2" data-mode="grid">');
        expect(grid).toContain('<div class="min-w-0">A</div>');
        expect(row).toContain('class="min-w-0 flex flex-col lg:flex-row gap-4 items-stretch" data-mode="row"');
        expect(row).toContain('<div class="min-w-0 flex-(--cell-size)" style="--cell-size:2">A</div>');
        expect(row).toContain('style="--cell-size:1">B</div>');
        expect(framed).toContain('class="min-w-0 mx-auto w-full max-w-narrow border border-line bg-panel rounded-panel-lg shadow-panel-md p-6"');
        expect(framed).toContain("grid-cols-3");

    });
    test("the pending state is a polite status that names itself for assistive technology and reveals after a beat", () => {

        const markup = html(<Pending label="Loading" />);

        expect(markup).toStartWith('<div role="status" aria-live="polite" class="grid min-h-96 animate-reveal place-items-center">');
        expect(markup).toContain('<span aria-hidden="true" class="size-glyph-xl animate-spin');
        expect(markup).toContain('<span class="sr-only">Loading</span>');

    });
    test("structured data is one json-ld script whose text can never close itself", () => {

        const markup = html(<Jsonld data={{ "@type": "WebPage", name: "</script><b>x" }} />);

        expect(markup.startsWith('<script type="application/ld+json">')).toBe(true);
        expect(markup).toContain('"name":"\\u003c/script>\\u003cb>x"');
        expect(markup.split("</script>")).toHaveLength(2);

    });

});
