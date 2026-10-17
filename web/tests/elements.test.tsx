import { describe, expect, test } from "bun:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Block from "@/elements/block";
import Button from "@/elements/button";
import Heading from "@/elements/heading";
import Jsonld from "@/elements/jsonld";
import Notice from "@/elements/notice";
import Shell from "@/elements/shell";

const html = ( node: ReactElement ): string => renderToStaticMarkup(node);
const layout = { width: "full", height: "auto", gap: 4, padding: 0, align: "stretch", tone: "default", radius: "none", shadow: "none" } as const;
const entries = [{ id: "a", node: "A" }, { id: "b", node: "B" }];

describe("elements", () => {

    test("a heading is one tag at its level, with an optional toned note inside it", () => {

        expect(html(<Heading id="t" level={1}>Title</Heading>)).toBe('<h1 id="t" class="heading" data-level="1" data-tone="default">Title</h1>');
        expect(html(<Heading level={3} tone="eyebrow">Sub</Heading>)).toContain("<h3 ");
        expect(html(<Heading level={2} note={{ text: "Live", tone: "success" }}>Hi</Heading>)).toBe(
            '<h2 class="heading" data-level="2" data-tone="default">Hi<small class="heading-note" data-tone="success">Live</small></h2>',
        );

    });
    test("a button is never a submit by accident and carries its tone, size and disabled state", () => {

        expect(html(<Button onClick={() => undefined}>Go</Button>)).toBe(
            '<button type="button" class="button" data-tone="primary" data-size="md">Go</button>',
        );
        expect(html(<Button type="submit" tone="danger" size="sm" disabled>Drop</Button>)).toContain('type="submit"');
        expect(html(<Button tone="ghost" disabled>Wait</Button>)).toContain(" disabled");

    });
    test("a notice speaks as an alert only when something failed, and its action is the shared button", () => {

        const failed = html(<Notice tone="failed" message="Broke" action="Retry" onAction={() => undefined} digest="d1" />);
        const missing = html(<Notice tone="missing" message="Gone" />);

        expect(failed).toContain('role="alert"');
        expect(failed).toContain('data-digest="d1"');
        expect(failed).toContain('<button type="button" class="button" data-tone="ghost" data-size="sm">Retry</button>');
        expect(missing).toContain('role="status"');
        expect(missing).not.toContain("<button");

    });
    test("the shell offers a skip link to the focusable main and renders only the parts it is given", () => {

        const bare = html(<Shell skip="Skip" page="home">Body</Shell>);
        const framed = html(<Shell skip="Skip" page="home" nav="N" sidebar="S" footer="F">Body</Shell>);

        expect(bare).toContain('<a href="#content" class="shell-skip">Skip</a>');
        expect(bare).toContain('<main id="content" tabindex="-1" class="shell-main">Body</main>');
        expect(bare).not.toContain("shell-nav");
        expect(framed).toContain('<header class="shell-nav">N</header>');
        expect(framed).toContain('<div class="shell-body" data-sidebar=""><aside class="shell-aside">S</aside>');
        expect(framed).toContain('<footer class="shell-footer">F</footer>');

    });
    test("a block lays its entries on a grid by default and shares one row by the declared sizes", () => {

        const grid = html(<Block {...layout} grid={{ base: 1, lg: 2 }} sizes={[]} entries={entries} />);
        const row = html(<Block {...layout} grid={1} sizes={[2, 1]} entries={entries} />);

        expect(grid).toContain('class="block-flow" data-mode="grid" data-gap="4" data-align="stretch" style="--grid-base:1;--grid-lg:2"');
        expect(grid).toContain('<div class="block-cell">A</div>');
        expect(row).toContain('data-mode="row"');
        expect(row).toContain('<div class="block-cell" data-sized="" style="--cell-size:2">A</div>');
        expect(row).toContain('style="--cell-size:1">B</div>');

    });
    test("structured data is one json-ld script whose text can never close itself", () => {

        const markup = html(<Jsonld data={{ "@type": "WebPage", name: "</script><b>x" }} />);

        expect(markup.startsWith('<script type="application/ld+json">')).toBe(true);
        expect(markup).toContain('"name":"\\u003c/script>\\u003cb>x"');
        expect(markup.split("</script>")).toHaveLength(2);

    });

});
