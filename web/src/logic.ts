// Plain functions for the pages: no React, no calls. Run `node web/src/logic.check.ts` to check them.
import type { Group, Left, Options, PlanResult, Profile, Semester } from "./api.ts";

export const termLabel = (term?: string | null) =>
  term ? `${term[5].toUpperCase()}${term.slice(6)} ${term.slice(0, 4)}` : "";

export type Suggestion = { id: "sooner" | "lighter" | "summer" | "winter" | "choose"; label: string };
/** The few next steps worth offering under a plan, in this order, at most three. */
export function suggestions(plan: PlanResult, options: Options, open: number): Suggestion[] {
  const out: Suggestion[] = [];
  const { fold_last_term: sooner, normal_load: lighter } = plan.pace ?? {};
  if (open > 0) out.push({ id: "choose", label: "Choose my open courses" });
  if (sooner) out.push({ id: "sooner", label: `Finish sooner (graduate ${termLabel(sooner.est_graduation_term)})` });
  if (lighter) out.push({ id: "lighter", label: `Lighter terms (graduate ${termLabel(lighter.est_graduation_term)})` });
  if (!options.include_summer) out.push({ id: "summer", label: "Add summer" });
  if (!options.include_winter) out.push({ id: "winter", label: "Add Winter Session" });
  return out.slice(0, 3);
}

/** What moved between two plans, in words: "BIOL 100 added to Spring 2027 · CSC 645 moved to Fall 2028". */
export function describeChange(before: Semester[], after: Semester[]): string {
  const where = (semesters: Semester[]) =>
    new Map(semesters.flatMap((s) => s.courses.filter((c) => typeof c === "string").map((c) => [c as string, s.term] as const)));
  const was = where(before);
  const now = where(after);
  const lines = [...now].flatMap(([code, term]) =>
    !was.has(code) ? [`${code} added to ${termLabel(term)}`] : was.get(code) !== term ? [`${code} moved to ${termLabel(term)}`] : [],
  );
  for (const [code, term] of was) if (!now.has(code)) lines.push(`${code} removed from ${termLabel(term)}`);
  return lines.join(" · ");
}

export type Mark = "complete" | "progress" | "incomplete" | "exception" | "warning";
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
