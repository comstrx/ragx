"use client";

import { held } from "engine/interact";
import { useEffect } from "react";
import { config } from "@/lib/spec/runtime";

export function useTitle ( page: string, action?: string | undefined ): void {

    useEffect(() => held(document, [action, page, config.content.name]), [action, page]);

}
