import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import Greeting from "@/components/greeting";

describe("components", () => {

    test("a greeting is one heading carrying the message and a toned note, at the level its screen gave it", () => {

        const primary = renderToStaticMarkup(<Greeting id="hello" message="Hello World" note="Live" tone="success" primary />);
        const nested  = renderToStaticMarkup(<Greeting id="hello" message="Hello World" note="Saved" tone="warning" primary={false} />);

        expect(primary).toBe(
            '<h1 id="hello" class="m-0 text-balance text-ink text-2xl font-bold tracking-tight" data-level="1">Hello World' +
                '<small class="mt-2 block text-sm font-semibold uppercase tracking-wide text-success" data-tone="success">Live</small></h1>',
        );
        expect(nested.startsWith("<h2 ")).toBe(true);
        expect(nested).toContain('data-tone="warning">Saved</small>');

    });

});
