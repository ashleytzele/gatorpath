// Run: node web/src/logic.check.ts
import assert from "node:assert/strict";
import { aiErrorText, blockOf, changeLine, countSection, coveredBy, describeChange, distinctMeetings, goalText, leftText, limitOf, offeredText, markOf, pathwayLine, plainWarning, restoreMissingSlots, shortRoom, splitWhy, suggestions, termLabel, warnedGroups, plannedLine, withoutCoveredSlots, withoutUrls, withPlanned } from "./logic.ts";

const g = (id: string, status: string) => ({ id, title: id, kind: "major", source: "", status, counted: [], in_progress: [] });
const term = (t: string, courses: (string | { slot: string; units: number })[]) => ({ term: t, courses });
const slot = { slot: "elective", units: 3 };
const planWith = (pace: object) => ({ semesters: [], warnings: [], pace: { terms: 8, load: "", planned_units: 0, min_terms_by_prereqs: 0, min_terms_by_units: 0, longest_chain: [], ...pace } });
const profile = { program: "bs-cs", completed: [{ code: "MATH 226", grade: "A" }] };
const envs = { group: "ge_4ud", term: "2027-spring", code: "ENVS 401", covers: ["sfss_esca", "sfss_gp"] };
assert.equal(coveredBy("sfss_esca", [envs])?.code, "ENVS 401");
assert.equal(coveredBy("sfss_gp", [envs])?.code, "ENVS 401");
assert.equal(coveredBy("ge_4ud", [envs]), undefined);
assert.deepEqual(withoutCoveredSlots([
  term("2027-spring", ["ENVS 401", { slot: "sfss_esca", units: 0 }]),
  term("2027-fall", [{ slot: "sfss_gp", units: 0 }]),
], [envs]), [term("2027-spring", ["ENVS 401"])]);
const initialGE = [term("2027-spring", [{ slot: "ge_4ud", units: 3 }]),
  term("2027-fall", [{ slot: "sfss_esca", units: 0 }, { slot: "sfss_gp", units: 0 }])];
const swappedGE = [term("2027-spring", ["AA S 323"]), term("2027-fall", [])];
assert.deepEqual(restoreMissingSlots(swappedGE, initialGE,
  [{ error: "requirement_not_covered", group: "sfss_esca", message: "Environmental Sustainability isn't covered" }], "2027-spring"),
  [term("2027-spring", ["AA S 323"]), term("2027-fall", [{ slot: "sfss_esca", units: 0 }])]);
assert.deepEqual(restoreMissingSlots([swappedGE[0]], initialGE,
  [{ error: "requirement_not_covered", group: "sfss_esca", message: "Environmental Sustainability isn't covered" }], "2027-spring"),
  [term("2027-spring", ["AA S 323", { slot: "sfss_esca", units: 0 }])]);
assert.equal(restoreMissingSlots(swappedGE, initialGE,
  [{ error: "prereq_not_met", message: "AA S 323 needs a prerequisite" }], "2027-spring"), swappedGE);
assert.equal(shortRoom("Thornton Hall 329"), "TH 329");
assert.equal(shortRoom("Humanities Building 384"), "HUM 384");
assert.equal(shortRoom("Online"), "Online");
const hybrid = [{ days: "Mo", time: "12:30 PM - 3:15 PM", where: "HSS Building 306" }, { days: "Mo", time: "12:30 PM - 3:15 PM", where: "Online" }];
assert.deepEqual(distinctMeetings(hybrid), [hybrid[0]]);
assert.deepEqual(distinctMeetings([...hybrid].reverse()), [hybrid[0]]);

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
assert.deepEqual(limitOf("You've asked the AI helper 5 times this hour. Try again in 39 minutes"), { hour: 0, day: 1 });
assert.deepEqual(limitOf("The AI helper reached its daily limit for everyone", { hour: 3, day: 9 }), { hour: 3, day: 0 });
assert.equal(limitOf("The AI helper isn't connected yet"), undefined);
assert.equal(aiErrorText("You've asked the AI helper 5 times this hour. Try again in 7 minutes; planning works without it."), "You've reached Gator AI's hourly limit. Come back in 7 minutes; planning works without it.");
assert.equal(aiErrorText("The AI helper has reached today's limit for everyone. It's back tomorrow; planning works without it."), "Gator AI's daily limit has been reached. Come back tomorrow; planning works without it.");
assert.equal(aiErrorText("The AI helper isn't connected yet"), "Gator AI isn't connected yet");
assert.equal(markOf(g("a", "satisfied"), true), "warning");
assert.equal(markOf(g("a", "waived"), false), "exception");
assert.equal(markOf(g("a", "in_progress"), false), "progress");
assert.equal(markOf(g("a", "remaining"), false), "incomplete");
assert.equal(markOf(g("a", "remaining"), false, true), "planned");
assert.equal(markOf(g("a", "in_progress"), false, true), "progress");
assert.equal(markOf({ ...g("a", "remaining"), in_progress: ["CSC 101"] }, false, true), "progress");
assert.equal(markOf(g("a", "remaining"), true, true), "warning");
assert.deepEqual(countSection([g("a", "satisfied"), g("b", "waived"), { ...g("c", "remaining"), in_progress: ["CSC 101"] }, g("d", "remaining")], new Set(["d"])), { done: 2, progress: 1, total: 4, warned: 1 });
assert.deepEqual(countSection([g("a", "satisfied"), { ...g("left", "waived"), waived_by: "not on the student's DPR" }], new Set(["left"])), { done: 1, progress: 0, total: 1, warned: 1 });
assert.equal(countSection([{ ...g("going", "in_progress"), in_progress: ["CSC 101"] }], new Set()).progress, 1);
assert.equal(countSection([{ ...g("done", "satisfied"), in_progress: ["CSC 101"] }], new Set()).progress, 0);
assert.equal(countSection([{ ...g("warned", "remaining"), in_progress: ["CSC 101"] }], new Set(["warned"])).progress, 0);
assert.equal(describeChange([term("2027-spring", [slot])], [term("2027-spring", ["BIOL 100"])]), "BIOL 100 added to Spring 2027");
assert.equal(describeChange([term("2027-spring", ["CSC 645"])], [term("2028-fall", ["CSC 645"])]), "CSC 645 moved to Fall 2028");
assert.equal(describeChange([term("2027-spring", ["CSC 645"])], [term("2027-spring", ["CSC 645"])]), "");
// Finish sooner folds the last term into the one before: its open choices move, and the line says so
const fold = [term("2030-spring", ["CSC 600", slot]), term("2030-fall", [slot, slot])];
const folded = [term("2030-spring", ["CSC 600", slot, slot, slot])];
assert.equal(describeChange(fold, folded), "2 open choices moved to Spring 2030");
assert.equal(changeLine(fold, folded, { valid: true, errors: [] }, "2030-spring").text, "2 open choices moved to Spring 2030 · graduate Spring 2030 · checked against the Bulletin");
assert.equal(describeChange([term("2028-fall", ["CSC 645"])], [term("2028-fall", [slot])]), "CSC 645 removed from Fall 2028 · 1 open choice added to Fall 2028");
const spread = (n: number) => [term("2028-fall", Array.from({ length: n }, (_, i) => `CSC ${600 + i}`))];
assert.equal(changeLine(spread(4), [term("2029-spring", ["CSC 600", "CSC 601", "CSC 602", "CSC 603", slot])], { valid: true, errors: [] }, "2029-spring", true).text.split(" · ")[0], "4 courses and 1 open choice moved");
assert.equal(changeLine(spread(1), spread(1), { valid: true, errors: [] }, "2028-fall", true).text.split(" · ")[0], "no course moved");
const before = [term("2027-spring", [slot])];
const after = [term("2027-spring", ["BIOL 100"])];
const ok = changeLine(before, after, { valid: true, errors: [] }, "2027-spring");
assert.equal(ok.kind, "ok");
assert.equal(ok.text, "BIOL 100 added to Spring 2027 · graduate Spring 2027 · checked against the Bulletin");
assert.deepEqual(ok.codes, ["BIOL 100"]);
const no = changeLine(before, after, { valid: false, errors: [{ message: "BIOL 100 needs CHEM 101 first" }, { message: "x" }] }, "2027-spring");
assert.equal(no.kind, "refused");
assert.equal(no.text, "Not changed · BIOL 100 needs CHEM 101 first");
const bad = changeLine(before, after, { valid: false, errors: [{ message: "BIOL 100 needs CHEM 101 first" }] }, "2027-spring", true);
assert.equal(bad.kind, "problem");
assert.ok(bad.text.includes("with a problem") && bad.text.includes("BIOL 100 needs CHEM 101 first"));
assert.deepEqual(bad.codes, ["BIOL 100"]);
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
assert.deepEqual(splitWhy("needed before CSC 220 in this plan; opens 2 senior-elective option(s): CSC 685, CSC 686"), { now: "Needed before CSC 220 in this plan", opens: "CSC 685, CSC 686" });
assert.deepEqual(splitWhy("Opens 1 senior-elective option(s): CSC 699; no slack: delaying it pushes back CSC 648"), { now: "No slack: delaying it pushes back CSC 648", opens: "CSC 699" });
assert.deepEqual(splitWhy(undefined), { now: "", opens: "" });
assert.equal(
  withoutUrls("Email cs-dept@sfsu.edu, or book a department advisor in Navigator (https://sfsu.campus.eab.com/), and ask for a senior advisor's approval before taking the course."),
  "Email cs-dept@sfsu.edu, or book a department advisor in Navigator, and ask for a senior advisor's approval before taking the course.",
);
assert.equal(withoutUrls("Schedule through Navigator at https://sfsu.campus.eab.com/. Email cs-dept@sfsu.edu if you can't access Navigator."), "Schedule through Navigator. Email cs-dept@sfsu.edu if you can't access Navigator.");
assert.equal(withoutUrls("Navigator, https://sfsu.campus.eab.com/"), "Navigator");
assert.equal(plannedLine(6, 15, [3, 3, 3]), "15 of 15 units planned");
assert.equal(plannedLine(undefined, 15, []), "0 of 15 units planned");
assert.equal(plannedLine(6, undefined, [3]), "");
assert.deepEqual(blockOf({ days: "Mo We", time: "10:00AM - 11:15AM" }, 8, 60), { top: 120, height: 75 });
assert.deepEqual(blockOf({ days: "Tu", time: "12:30PM - 1:20PM" }, 8, 60), { top: 270, height: 50 });
assert.equal(offeredText({ fall: [4, 4], spring: [5, 5], summer: [4, 4], last: "2027-spring" }), "Offered every fall, every spring and every summer · last Spring 2027");
assert.equal(offeredText({ fall: [1, 4], spring: [2, 5], summer: [0, 4], last: "2027-spring" }), "Offered 1 of the last 4 falls and 2 of the last 5 springs · last Spring 2027");
assert.equal(offeredText({ summer: [0, 4] }), "Not offered in recent terms");
assert.equal(offeredText(null), "No offering history here: check Class Search");
assert.equal(blockOf({ days: "Mo" }, 8, 60), null);
assert.equal(blockOf({ time: "TBA" }, 8, 60), null);
console.log("logic.check: ok");
