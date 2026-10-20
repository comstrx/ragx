import "@/styles/globals.css";
import "@spec/theme.css";

import Script from "next/script";
import type { ReactNode } from "react";
import Document from "@/elements/document";
import { siteMetadata, siteViewport } from "@/lib/seo";
import { type Locale, languages } from "@/lib/spec/languages";
import { routing } from "@/lib/spec/runtime";
import { choose } from "@/lib/std/base";
import { Providers } from "./providers.tsx";

type Props = { children: ReactNode; params: Promise<{ locale: string }> };

export const dynamicParams = false;

export function generateStaticParams (): { locale: Locale }[] {

    return routing.locales.map(( locale ) => ({ locale }));

}
export const metadata = siteMetadata();
export const viewport = siteViewport();

export default async function WebLayout ({ children, params }: Props) {

    const locale = choose(routing.locales, (await params).locale, routing.defaultLocale);

    return (

        <Document locale={locale} direction={languages[locale].direction}>

            <Script src="/_generated/boot.js" strategy="beforeInteractive" />

            <Providers>{children}</Providers>

        </Document>

    );

}
