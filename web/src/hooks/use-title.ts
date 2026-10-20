"use client";

import { useEffect } from "react";
import { config } from "@/lib/spec/runtime";
import { held } from "@/lib/std/screen";

export function useTitle ( page: string, action?: string | undefined ): void {

    useEffect(() => held(document, [action, page, config.content.name]), [action, page]);

}
