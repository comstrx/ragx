import { describe, expect, test } from "bun:test";
import type { ReactNode } from "react";
import { renderToString } from "react-dom/server";
import Greeting from "@/components/greeting";
import { PreferencesProvider } from "@/stores/preferences";

function render ( node: ReactNode ): string {

    return renderToString(<PreferencesProvider>{node}</PreferencesProvider>);

}

describe("mobile components", () => {

    test("the greeting is the page heading when primary and a section heading otherwise, with its note", () => {

        const primary = render(<Greeting id="hello" message="Hello World" note="Answered by the api" tone="success" primary />);
        const nested = render(<Greeting id="hello" message="Hello World" note="Showing the saved answer" tone="warning" primary={false} />);

        expect(primary).toContain('<h1 dir="auto" aria-level="1" role="heading"');
        expect(primary).toContain(">Hello World</h1>");
        expect(primary).toContain(">Answered by the api<");
        expect(nested).toContain('<h2 dir="auto" aria-level="2" role="heading"');
        expect(nested).toContain(">Showing the saved answer<");
        expect(primary).toContain('id="hello"');

    });

});
