// Run: node web/src/logic.check.ts
import assert from "node:assert/strict";
import { changeLine, countSection, describeChange, goalText, leftText, markOf, pathwayLine, plainWarning, suggestions, termLabel, warnedGroups, withPlanned } from "./logic.ts";

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
const before = [term("2027-spring", [slot])];
const after = [term("2027-spring", ["BIOL 100"])];
const ok = changeLine(before, after, { valid: true, errors: [] }, "2027-spring");
assert.equal(ok.kind, "ok");
assert.equal(ok.text, "BIOL 100 added to Spring 2027 · graduate Spring 2027 · checked against the Bulletin");
assert.deepEqual(ok.codes, ["BIOL 100"]);
const no = changeLine(before, after, { valid: false, errors: [{ message: "BIOL 100 needs CHEM 101 first" }, { message: "x" }] }, "2027-spring");
assert.equal(no.kind, "refused");
assert.equal(no.text, "Not changed · BIOL 100 needs CHEM 101 first");
assert.equal(suggestions(planWith({ normal_load: { max_units_per_term: 12, est_graduation_term: "2030-fall" } }), { max_units_per_term: 12, include_summer: true, include_winter: true }, 0).length, 0);
const both = { include_summer: true, include_winter: true };
assert.deepEqual(suggestions(planWith({}), both, 0), []);
assert.deepEqual(suggestions(planWith({}), {}, 0).map((s) => s.label), ["Add summer", "Add Winter Session"]);
assert.equal(suggestions(planWith({ fold_last_term: { est_graduation_term: "2029-spring" }, normal_load: { max_units_per_term: 12, est_graduation_term: "2030-fall" } }), {}, 1)[0].id, "choose");
assert.deepEqual(suggestions(planWith({ fold_last_term: { est_graduation_term: "2029-spring" } }), { include_summer: true }, 2).map((s) => s.id), ["choose", "sooner", "winter"]);
assert.equal(suggestions(planWith({ normal_load: { max_units_per_term: 12, est_graduation_term: "2030-fall" } }), {}, 0)[0].label, "Lighter terms (graduate Fall 2030)");
assert.equal(withPlanned(profile, [term("2027-spring", ["CSC 256"])]).completed!.at(-1)!.code, "CSC 256");
const imported = { catalog_year: "2026-27", profile, remaining: null, cross_check: [], warnings: [], see_advisor: [], warnings_by_group: { ge_4: ["…"] } };
assert.deepEqual(warnedGroups({ ...profile, not_on_dpr: ["ge_2"] }, imported), new Set(["ge_2", "ge_4"]));
assert.deepEqual(warnedGroups(profile, null), new Set());
assert.equal(
  plainWarning("CSC 220: the DPR says done, GatorPath says needed. The DPR wins; ask an advisor if it looks wrong, and tell GatorPath if its rule is the one that's off"),
  "CSC 220: your DPR says done, GatorPath says needed. Your DPR wins; ask an advisor if it looks wrong.",
);
console.log("logic.check: ok");
