import process from "node:process";
import { run } from "mitata";
import { report } from "./core.ts";

export type Budgets = Readonly<Record<string, number>>;
export type Trial = { alias: string; runs: readonly { name: string; stats?: { p99: number } | undefined; error?: unknown }[] };

const micro = 1000;

export function breaches ( trials: readonly Trial[], budgets: Budgets, scale = 1 ): string[] {

    const named = new Set(trials.flatMap(( trial ) => trial.runs.map(( entry ) => entry.name)));
    const unused = Object.keys(budgets).filter(( name ) => !named.has(name)).map(( name ) => `${name}: a budget without a bench.`);
    const measured = trials.flatMap(( trial ) => trial.runs.flatMap(( entry ) => {

        const budget = budgets[entry.name];

        if ( !entry.stats ) return [`${entry.name}: the bench failed: ${String(entry.error)}`];

        const p99 = entry.stats.p99 / micro;

        if ( budget === undefined ) return [`${entry.name}: a bench without a p99 budget (measured ${p99.toFixed(2)}µs).`];

        const limit = budget * scale;

        return p99 > limit ? [`${entry.name}: p99 ${p99.toFixed(2)}µs is over its budget of ${limit.toFixed(2)}µs.`] : [];

    }));

    return [...measured, ...unused];

}
export async function measured ( budgets: Budgets ): Promise<void> {

    const scale = Number(process.env.BENCH_SCALE ?? "1") || 1;
    const { benchmarks } = await run();
    const problems = breaches(benchmarks, budgets, scale);

    report(problems.length ? problems.join("\n") : `Benches: ${Object.keys(budgets).length} p99 budgets held (scale ${scale}).`);
    process.exitCode = problems.length ? 1 : 0;

}
