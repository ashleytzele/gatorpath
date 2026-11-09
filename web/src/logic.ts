// Plain functions for the pages: no React, no calls. Run `node web/src/logic.check.ts` to check them.
import type { Checked, Group, ImportResult, Left, Meeting, Offered, Options, Pick, PlanError, PlanResult, Profile, Semester } from "./api.ts";

export const termLabel = (term?: string | null) =>
  term ? `${term[5].toUpperCase()}${term.slice(6)} ${term.slice(0, 4)}` : "";
export const unitText = (units?: number | string) => `${units} ${Number(units) === 1 ? "unit" : "units"}`;
export const NOT_ON_DPR = "not on the student's DPR"; // the engine's waived_by for a requirement the student left out
export const coveredBy = (group: string, picks: Pick[]) => picks.find((pick) => pick.covers.includes(group));
export const withoutCoveredSlots = (semesters: Semester[], picks: Pick[]) =>
  semesters.map((semester) => ({
    ...semester,
    courses: semester.courses.filter((course) => typeof course === "string" || !coveredBy(course.slot, picks)),
  })).filter((semester) => semester.courses.length);

/** A swap can lose an extra requirement that the old course covered. Reopen its original choice. */
export function restoreMissingSlots(semesters: Semester[], baseline: Semester[], errors: PlanError[], fallbackTerm: string): Semester[] {
  let restored = semesters;
  for (const group of new Set(errors.filter((e) => e.error === "requirement_not_covered").map((e) => e.group).filter((id): id is string => !!id))) {
    const originals = baseline.flatMap((s) => s.courses.flatMap((course) =>
      typeof course !== "string" && course.slot === group ? [{ term: s.term, course }] : []));
    const present = restored.flatMap((s) => s.courses).filter((course) => typeof course !== "string" && course.slot === group).length;
    const missing = originals[present];
    if (!missing) continue;
    if (restored === semesters) restored = semesters.map((s) => ({ ...s, courses: [...s.courses] }));
    const term = restored.find((s) => s.term === missing.term) ?? restored.find((s) => s.term === fallbackTerm);
    term?.courses.push({ ...missing.course });
  }
  return restored;
}

const BUILDINGS: Record<string, string> = {
  "Burk Hall": "BH", "Business Building": "BUS", "Creative Arts Building": "CA", "Creative Arts": "CA",
  "Downtown Campus": "DTC", "Ethnic Studies/Psych Bldg": "EP", "Fine Arts Building": "FA",
  "Gymnasium": "GYM", "HSS Building": "HSS", "Hensill Hall": "HH", "Humanities Building": "HUM",
  "J.P. Leonard Library": "LIB", "Marcus Hall": "MH", "Sci & Engr Innov Center": "SEIC",
  "Science Building": "SCI", "Thornton Hall": "TH",
};
export function shortRoom(where?: string) {
  if (!where) return "";
  const building = Object.keys(BUILDINGS).find((name) => where.startsWith(`${name} `));
  return building ? `${BUILDINGS[building]} ${where.slice(building.length + 1)}` : where;
}
export function distinctMeetings(meetings: Meeting[]) {
  const byTime = new Map<string, Meeting>();
  for (const meeting of meetings) {
    const key = `${meeting.days ?? ""}|${meeting.time ?? ""}`;
    const previous = byTime.get(key);
    if (!previous || (/online/i.test(previous.where ?? "") && !/online/i.test(meeting.where ?? ""))) byTime.set(key, meeting);
  }
  return [...byTime.values()];
}

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

/** Open choices that landed in a term: "2 open choices moved to Spring 2030" ("added to" when none left another term). */
const slotMoves = (before: Semester[], after: Semester[]) => {
  const open = (s: Semester) => s.courses.filter((c) => typeof c !== "string").length;
  const was = new Map(before.map((s) => [s.term, open(s)]));
  const now = new Map(after.map((s) => [s.term, open(s)]));
  const left = [...was].some(([term, n]) => n > (now.get(term) ?? 0));
  return after.flatMap((s) => {
    const n = open(s) - (was.get(s.term) ?? 0);
    return n > 0 ? [{ n, text: `${n} open ${n === 1 ? "choice" : "choices"} ${left ? "moved" : "added"} to ${termLabel(s.term)}` }] : [];
  });
};

/** What moved between two plans, in words: "BIOL 100 added to Spring 2027 · CSC 645 moved to Fall 2028". */
export function describeChange(before: Semester[], after: Semester[]): string {
  const { moved, removed } = moves(before, after);
  return [...moved.map((m) => m.text), ...removed, ...slotMoves(before, after).map((m) => m.text)].join(" · ");
}

/** One chat line. "me" and "ai" go to the model as the conversation; "ok" and "refused" are only shown. */
export type ChatLine = { kind: "me" | "ai" | "ok" | "refused" | "problem"; text: string; codes?: string[] };

/** The one line a plan change gets: what moved, or why the check said no (the first error). `applied`: the change is
 * already in force (an AI answer, a record edit), so a failed check is a problem to show, not a refusal. */
export function changeLine(before: Semester[], after: Semester[], check: Checked, graduation: string, applied = false): ChatLine {
  const { moved, removed } = moves(before, after);
  const slots = slotMoves(before, after);
  const courses = moved.length + removed.length;
  const open = slots.reduce((t, m) => t + m.n, 0);
  const many = [courses && `${courses} ${courses === 1 ? "course" : "courses"}`, open && `${open} open ${open === 1 ? "choice" : "choices"}`];
  const change = // a rebuilt plan can move many
    courses + slots.length > 4 ? `${many.filter(Boolean).join(" and ")} moved` : describeChange(before, after) || "no course moved";
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

/** The rules' booking text with its URLs taken out (the page shows them as links), and the "at", comma or brackets
 * that led to them: "… in Navigator (https://…), and ask …" -> "… in Navigator, and ask …". */
export const withoutUrls = (text: string) =>
  text
    .replace(/(?:\s+at|,)?\s*\(?https?:\/\/[^\s()]*[^\s().,;:]\)?/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();

export type Mark = "complete" | "progress" | "planned" | "incomplete" | "exception" | "warning";
export const markOf = (g: Group, warned: boolean, planned = false): Mark =>
  warned ? "warning" : g.status === "satisfied" ? "complete" : g.status === "waived" ? "exception" : g.status === "in_progress" || g.in_progress.length > 0 ? "progress" : planned ? "planned" : "incomplete";

/** A section's count: done = complete + exception; a requirement left out of the plan is excluded from the total. */
export function countSection(groups: Group[], warned: Set<string>) {
  const active = groups.filter((g) => g.waived_by !== NOT_ON_DPR);
  const marks = active.map((g) => markOf(g, warned.has(g.id)));
  return {
    done: marks.filter((m) => m === "complete" || m === "exception").length,
    progress: marks.filter((m) => m === "progress").length,
    total: active.length,
    warned: groups.filter((g) => warned.has(g.id)).length,
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

/** What an AI refusal says about the limits: the hour or the day is used up (the other stays as known, or open). */
export const limitOf = (refusal: string, left?: Left): Left | undefined =>
  /limit for everyone/.test(refusal)
    ? { hour: left?.hour ?? 1, day: 0 }
    : /times this hour/.test(refusal)
      ? { hour: 0, day: left?.day ?? 1 }
      : left;

export function aiErrorText(text: string) {
  if (/times this hour/.test(text)) {
    const wait = text.match(/Try again in (\d+) minutes?/);
    return `You've reached Gator AI's hourly limit. Come back ${wait ? `in ${wait[1]} minute${wait[1] === "1" ? "" : "s"}` : "in an hour"}; planning works without it.`;
  }
  if (/limit for everyone/.test(text)) return "Gator AI's daily limit has been reached. Come back tomorrow; planning works without it.";
  return text.replace(/The AI helper/g, "Gator AI").replace(/AI helper/g, "Gator AI");
}

/** null when unknown or plenty left; else the smaller of the hour and the day. */
export function leftText(left?: Left): string | null {
  if (!left) return null;
  const today = left.day < left.hour;
  const n = today ? left.day : left.hour;
  return n > 5 ? null : `${n} ${n === 1 ? "question" : "questions"} left ${today ? "today" : "this hour"}`;
}

/** "15 of 15 units planned": what's done plus every row the plan holds for the group, out of what it needs. "" when the group names no total. */
export function plannedLine(done: number | undefined, needed: number | undefined, rowUnits: number[]) {
  if (!needed) return "";
  return `${(done ?? 0) + rowUnits.reduce((t, u) => t + u, 0)} of ${needed} units planned`;
}

/** When a course ran, in words: "Offered every fall and 2 of the last 5 springs · last Spring 2027". */
export function offeredText(o?: Offered | null) {
  if (!o) return "No offering history here: check Class Search";
  const ran = (["fall", "spring", "summer"] as const).flatMap((season) => {
    const [n, of] = o[season] ?? [0, 0];
    return n ? [n === of ? `every ${season}` : `${n} of the last ${of} ${season}s`] : [];
  });
  const when = ran.length > 1 ? `${ran.slice(0, -1).join(", ")} and ${ran[ran.length - 1]}` : ran[0];
  return [when ? `Offered ${when}` : "Not offered in recent terms", o.last && `last ${termLabel(o.last)}`].filter(Boolean).join(" · ");
}

/** "10:00AM" -> 10, "1:20PM" -> 13.33 (hours since midnight). */
export function hourOf(text?: string) {
  const m = text?.match(/(\d+):(\d+)\s*(AM|PM)/);
  return m ? (Number(m[1]) % 12) + (m[3] === "PM" ? 12 : 0) + Number(m[2]) / 60 : null;
}
export function hours(meeting: Meeting) {
  const [from, to] = (meeting.time ?? "").split(" - ");
  const start = hourOf(from);
  const end = hourOf(to);
  return start === null || end === null ? null : { start, end };
}
/** Where a meeting sits on the week: px from the first hour, and its height. null when it has no set time. */
export function blockOf(meeting: Meeting, start: number, hourPx: number) {
  const t = hours(meeting);
  return t ? { top: Math.round((t.start - start) * hourPx), height: Math.round((t.end - t.start) * hourPx) } : null;
}
