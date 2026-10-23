"use client";

import type { FeatureProps } from "@/lib/spec/feature";
import Welcome, { type Options } from "./components/welcome.tsx";

export default function Hello ( props: FeatureProps<Options> ) {

    return <Welcome {...props} />;

}
