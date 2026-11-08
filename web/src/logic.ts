// Plain functions for the pages: no React, no calls. Run `node web/src/logic.check.ts` to check them.
import type { Checked, Group, ImportResult, Left, Options, PlanResult, Profile, Semester } from "./api.ts";

export const termLabel = (term?: string | null) =>
  term ? `${term[5].toUpperCase()}${term.slice(6)} ${term.slice(0, 4)}` : "";
export const unitText = (units?: number | string) => `${units} ${Number(units) === 1 ? "unit" : "units"}`;
export const NOT_ON_DPR = "not on the student's DPR"; // the engine's waived_by for a requirement the student left out

export type Suggestion = { id: "sooner" | "lighter" | "summer" | "winter" | "choose"; label: string };
/** The few next steps worth offering under a plan, in this order, at most three. */
export function suggestions(plan: PlanResult, options: Options, open: number): Suggestion[] {
  const out: Suggestion[] = [];
  const { fold_last_term: sooner, normal_load: lighter } = plan.pace ?? {};
  if (open > 0) out.push({ id: "choose", label: "Choose my open courses" });
  if (sooner) out.push({ id: "sooner", label: `Finish sooner (graduate ${termLabel(sooner.est_graduation_term)})` });
  if (lighter && options.max_units_per_term !== lighter.max_units_per_term) out.push({ id: "lighter", label: `Lighter terms (graduate ${termLabel(lighter.est_graduation_term)})` });
  if (!options.include_summer) out.push({ id: "summer", label: "Add summer" });
  if (!options.include_winter) out.push({ id: "winter", label: "Add Winter Session" });
  return out.slice(0, 3);
}

/** Courses that appeared or moved between two plans, with where they went. */
const moves = (before: Semester[], after: Semester[]) => {
  const where = (semesters: Semester[]) =>
    new Map(semesters.flatMap((s) => s.courses.filter((c) => typeof c === "string").map((c) => [c as string, s.term] as const)));
  const was = where(before);
  const now = where(after);
  const moved = [...now].flatMap(([code, term]) =>
    !was.has(code) ? [{ code, text: `${code} added to ${termLabel(term)}` }] : was.get(code) !== term ? [{ code, text: `${code} moved to ${termLabel(term)}` }] : [],
  );
  const removed = [...was].filter(([code]) => !now.has(code)).map(([code, term]) => `${code} removed from ${termLabel(term)}`);
  return { moved, removed };
};

/** What moved between two plans, in words: "BIOL 100 added to Spring 2027 · CSC 645 moved to Fall 2028". */
export function describeChange(before: Semester[], after: Semester[]): string {
  const { moved, removed } = moves(before, after);
  return [...moved.map((m) => m.text), ...removed].join(" · ");
}

/** One chat line. "me" and "ai" go to the model as the conversation; "ok" and "refused" are only shown. */
export type ChatLine = { kind: "me" | "ai" | "ok" | "refused" | "problem"; text: string; codes?: string[] };

/** The one line a plan change gets: what moved, or why the check said no (the first error). `applied`: the change is
 * already in force (an AI answer, a record edit), so a failed check is a problem to show, not a refusal. */
export function changeLine(before: Semester[], after: Semester[], check: Checked, graduation: string, applied = false): ChatLine {
  const { moved, removed } = moves(before, after);
  const n = moved.length + removed.length;
  const change = n > 4 ? `${n} courses moved` : describeChange(before, after) || "no course moved"; // a rebuilt plan can move many
  const codes = moved.map((m) => m.code);
  const first = check.errors[0]?.message ?? "the plan did not pass the check";
  if (!check.valid)
    return applied
      ? { kind: "problem", text: `Plan updated, with a problem · ${change} · ${first}`, codes }
      : { kind: "refused", text: `Not changed · ${first}` };
  return { kind: "ok", text: `${change} · graduate ${termLabel(graduation)} · checked against the Bulletin`, codes };
}

/** The planner's `why` (clauses joined by "; ") for the course card: what it unlocks, as a course list, and the rest. */
export function splitWhy(why?: string): { now: string; opens: string } {
  const parts = (why ?? "").split("; ").filter(Boolean);
  const isOpens = (p: string) => /^opens \d+ senior-elective option\(s\): /i.test(p);
  const now = parts.filter((p) => !isOpens(p)).join("; ").replace(/\(s\)/g, "");
  return {
    now: now.charAt(0).toUpperCase() + now.slice(1),
    opens: parts.find(isOpens)?.replace(/^[^:]*: /, "") ?? "",
  };
}

export type Mark ="complete" | "progress" | "incomplete" | "exception" | "warning";
export const markOf = (g: Group, warned: boolean): Mark =>
  warned ? "warning" : g.status === "satisfied" ? "complete" : g.status === "waived" ? "exception" : g.status === "in_progress" ? "progress" : "incomplete";

/** A section's count: done = complete + exception; a warned group counts only as warned. */
export function countSection(groups: Group[], warned: Set<string>) {
  const marks = groups.map((g) => markOf(g, warned.has(g.id)));
  return {
    done: marks.filter((m) => m === "complete" || m === "exception").length,
    total: groups.length,
    warned: marks.filter((m) => m === "warning").length,
  };
}

/** Requirements with something to check against the DPR: left out because it doesn't list them, or a disagreement. */
export const warnedGroups = (profile: Profile, imported: ImportResult | null) =>
  new Set([...(profile.not_on_dpr ?? []), ...Object.keys(imported?.warnings_by_group ?? {})]);

/** A cross-check line as the student reads it: "your DPR", without the note to the AI client. */
export const plainWarning = (text: string) =>
  text
    .replace(/\b([Tt])he DPR\b/g, (_, t) => `${t === "T" ? "Your" : "your"} DPR`)
    .replace(/, and tell GatorPath if its rule is the one that's off$/, ".");

export function goalText(interests: string[], after: string[]): string {
  const mine = interests.filter((i) => i !== "Not sure yet").join(", ");
  const later = after.filter((a) => a !== "Not sure yet").join(", ");
  return [mine, later && `after graduating: ${later}`].filter(Boolean).join("; ");
}

export function pathwayLine(courses: { code: string; title: string }[]): string {
  const last = courses[courses.length - 1];
  if (!last) return "";
  const main = `${last.title} (${last.code})`;
  if (courses.length === 1) return `You start with ${main} in your first term.`;
  const first = courses.slice(0, -1).map((c) => c.code);
  return `You take ${first.length > 1 ? `${first.slice(0, -1).join(", ")} and ${first[first.length - 1]}` : first[0]} first, then ${main}.`;
}

/** The profile as if every planned course were done (grade "A"), for the "With your plan" audit. */
export function withPlanned(profile: Profile, semesters: Semester[]): Profile {
  const planned = semesters.flatMap((s) =>
    s.courses.filter((c) => typeof c === "string").map((code) => ({ code: code as string, grade: "A", term: s.term })),
  );
  return { ...profile, completed: [...(profile.completed ?? []), ...planned] };
}

/** null when unknown or plenty left; else the smaller of the hour and the day. */
export function leftText(left?: Left): string | null {
  if (!left) return null;
  const today = left.day < left.hour;
  const n = today ? left.day : left.hour;
  return n > 5 ? null : `${n} ${n === 1 ? "question" : "questions"} left ${today ? "today" : "this hour"}`;
}
