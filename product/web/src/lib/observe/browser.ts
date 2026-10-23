"use client";

import { createObserver } from "engine/api";
import { uuid } from "engine/base";

export const { trace, observeCall, flushMetrics, reportError } = createObserver({
    trace: uuid(),
    slow: 3000,
    send: () => undefined,
    watch: () => undefined,
});
