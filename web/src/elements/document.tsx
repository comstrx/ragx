import type { ReactNode } from "react";

type Props = { locale: string; direction?: "ltr" | "rtl"; children: ReactNode };

export default function Document ({ locale, direction = "ltr", children }: Props) {

    return (

        <html lang={locale} dir={direction} suppressHydrationWarning>

            <body>{children}</body>

        </html>

    );

}
