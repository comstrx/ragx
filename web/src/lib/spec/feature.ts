import type { ReactNode } from "react";
import type { FeatureProps as Props, Route as Routed } from "@/lib/std/screen";
import type { CompiledPort } from "@/lib/std/spec";
import type { Localized } from "@/lib/std/translate";
import type { CompiledScreen } from "./surface.ts";

export type Route = Routed;
export type Screen = Localized<CompiledScreen>;
export type Ports = Record<string, CompiledPort>;
export type Options = Record<string, unknown>;
export type FeatureProps<O extends Options = Options> = Props<O, Screen, ReactNode>;
