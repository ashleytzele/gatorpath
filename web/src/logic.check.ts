// Run: node web/src/logic.check.ts
import assert from "node:assert/strict";
import { countSection, describeChange, goalText, leftText, markOf, pathwayLine, suggestions, termLabel, withPlanned } from "./logic.ts";

const g = (id: string, status: string) => ({ id, title: id, kind: "major", source: "", status, counted: [], in_progress: [] });
const term = (t: string, courses: (string | { slot: string; units: number })[]) => ({ term: t, courses });
const slot = { slot: "elective", units: 3 };
const planWith = (pace: object) => ({ semesters: [], warnings: [], pace: { terms: 8, load: "", planned_units: 0, min_terms_by_prereqs: 0, min_terms_by_units: 0, longest_chain: [], ...pace } });
const profile = { program: "bs-cs", completed: [{ code: "MATH 226", grade: "A" }] };

assert.equal(termLabel("2027-spring"), "Spring 2027");
assert.equal(pathwayLine([{ code: "MATH 226", title: "Calculus I" }]), "You start with Calculus I (MATH 226) in your first term.");
assert.equal(pathwayLine([{ code: "MATH 197", title: "A" }, { code: "MATH 198", title: "B" }, { code: "MATH 226", title: "Calculus I" }]), "You take MATH 197 and MATH 198 first, then Calculus I (MATH 226).");
assert.equal(goalText(["Data Science", "Not sure yet"], ["Graduate school"]), "Data Science; after graduating: Graduate school");
assert.equal(goalText(["AI / Machine Learning", "Data Science"], []), "AI / Machine Learning, Data Science");
assert.equal(goalText(["Not sure yet"], []), "");
assert.equal(leftText(undefined), null);
assert.equal(leftText({ hour: 9, day: 20 }), null);
assert.equal(leftText({ hour: 1, day: 20 }), "1 question left this hour");
assert.equal(leftText({ hour: 4, day: 3 }), "3 questions left today");
assert.equal(markOf(g("a", "satisfied"), true), "warning");
assert.equal(markOf(g("a", "waived"), false), "exception");
assert.equal(markOf(g("a", "in_progress"), false), "progress");
assert.equal(markOf(g("a", "remaining"), false), "incomplete");
assert.deepEqual(countSection([g("a", "satisfied"), g("b", "waived"), g("c", "in_progress"), g("d", "remaining")], new Set(["d"])), { done: 2, total: 4, warned: 1 });
assert.equal(describeChange([term("2027-spring", [slot])], [term("2027-spring", ["BIOL 100"])]), "BIOL 100 added to Spring 2027");
assert.equal(describeChange([term("2027-spring", ["CSC 645"])], [term("2028-fall", ["CSC 645"])]), "CSC 645 moved to Fall 2028");
assert.equal(describeChange([term("2027-spring", ["CSC 645"])], [term("2027-spring", ["CSC 645"])]), "");
const both = { include_summer: true, include_winter: true };
assert.deepEqual(suggestions(planWith({}), both, 0), []);
assert.deepEqual(suggestions(planWith({}), {}, 0).map((s) => s.label), ["Add summer", "Add Winter Session"]);
assert.equal(suggestions(planWith({ fold_last_term: { est_graduation_term: "2029-spring" }, normal_load: { est_graduation_term: "2030-fall" } }), {}, 1)[0].id, "choose");
assert.deepEqual(suggestions(planWith({ fold_last_term: { est_graduation_term: "2029-spring" } }), { include_summer: true }, 2).map((s) => s.id), ["choose", "sooner", "winter"]);
assert.equal(suggestions(planWith({ normal_load: { est_graduation_term: "2030-fall" } }), {}, 0)[0].label, "Lighter terms (graduate Fall 2030)");
assert.equal(withPlanned(profile, [term("2027-spring", ["CSC 256"])]).completed!.at(-1)!.code, "CSC 256");
console.log("logic.check: ok");
