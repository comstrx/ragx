import "@/styles/tokens.css";
import "@/styles/globals.css";

import type { ReactNode } from "react";
import Document from "@/elements/document";

export default function RootLayout ({ children }: { children: ReactNode }) {

    return <Document locale="en">{children}</Document>;

}
