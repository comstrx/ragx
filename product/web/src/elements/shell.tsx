import { variants } from "engine/style";
import type { ReactNode } from "react";

type Props = { nav?: ReactNode; sidebar?: ReactNode; footer?: ReactNode; children: ReactNode; skip: string; page: string };

const skipper = [
    "sr-only rounded-control-md bg-panel px-4 py-2 text-ink shadow-overlay",
    "focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-(--layer-toast)",
].join(" ");
const aside = "overflow-y-auto border-b border-line bg-panel px-4 py-3 lg:w-aside lg:shrink-0 lg:border-e lg:border-b-0 lg:py-6";
const body = variants("flex min-w-0 flex-1", {
    sidebar: { off: "", on: "mx-auto w-full max-w-wide flex-col lg:flex-row" },
}, { sidebar: "off" });

export default function Shell ({ nav, sidebar, footer, children, skip, page }: Props) {

    return (

        <div className="flex min-h-screen flex-col" data-page={page}>

            <a href="#content" className={skipper}>{skip}</a>

            {nav ? <header className="sticky top-0 z-(--layer-sticky) border-b border-line bg-panel">{nav}</header> : null}

            <div className={body({ sidebar: sidebar ? "on" : "off" })} data-sidebar={sidebar ? "" : undefined}>

                {sidebar ? (

                    <aside data-scroll="" className={aside}>

                        {sidebar}

                    </aside>

                ) : null}

                <main id="content" tabIndex={-1} className="min-w-0 flex-1 outline-none">{children}</main>

            </div>

            {footer ? <footer className="border-t border-line bg-panel">{footer}</footer> : null}

        </div>

    );

}
