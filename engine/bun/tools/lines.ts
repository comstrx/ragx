import { resolve } from "node:path";
import { lineIssues, report, task } from "engine/tooling";

const columns = 150;
const sources = ["packages", "tests", "benches", "tools"];
const root = resolve(import.meta.dir, "..");

task(import.meta.url, () => {

    const problems = sources.flatMap(( source ) => lineIssues(resolve(root, source), source, columns));

    if ( problems.length ) throw new Error(problems.join("\n"));

    report(`Lines: no source line is wider than ${columns} columns.`);

});
