"use client";

import { createObserver } from "@/lib/std/api";
import { uuid } from "@/lib/std/base";

export const { trace, observeCall, flushMetrics, reportError } = createObserver({
    trace: uuid(),
    slow: 3000,
    send: () => undefined,
    watch: () => undefined,
});
