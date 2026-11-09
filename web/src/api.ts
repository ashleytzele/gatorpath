// The server's fields as the engine returns them. The web app keeps the current plan in this tab's session storage.
export type Slot = { slot: string; units: number; upper_division?: boolean };
export type Semester = {
  term: string;
  courses: (string | Slot)[];
  units?: number;
  max_units?: number;
  why?: Record<string, string>;
};
export type Plan = { semesters: Semester[] };
export type Taken = { code: string; grade: string; term?: string; transfer?: boolean; units?: number; credit?: string };
export type Options = {
  goal?: string;
  graduate_by?: string;
  max_units_per_term?: number;
  include_summer?: boolean;
  include_winter?: boolean;
  f1?: boolean;
  qr_pathway?: string;
  start_term?: string;
};
export type Left = { hour: number; day: number };
export type Profile = Options & {
  sf_state_gpa?: number;
  program: string;
  catalog_year?: string;
  completed?: Taken[];
  in_progress?: string[];
  gpa?: number;
  not_on_dpr?: string[];
  [field: string]: unknown;
};
export type Advisor = {
  role: string;
  who: string;
  why: string[];
  link?: string;
  how_to_book?: string;
  contact?: string;
  location?: string;
};
export type CourseInfo = { title: string; units: number | string; source_page: number };
export type Group = {
  id: string;
  title: string;
  kind: string;
  source: string;
  status: string;
  counted: string[];
  in_progress: string[];
  remaining?: string[];
  units_done?: number;
  units_needed?: number;
  waived_by?: string;
  quote?: string;
  min_units_from?: { subject: string; units: number; done: number };
  met_by?: string;
};
export type Total = { value: number; needed?: number; max?: number; ok: boolean };
export type Audit = {
  catalog_year: string;
  program: string;
  complete: boolean;
  groups: Group[];
  totals: Record<string, Total> & { units_in_progress: number; upper_division_units_in_progress?: number };
  warnings: string[];
  see_advisor: Advisor[];
  courses: Record<string, CourseInfo>;
  directory?: Advisor | null; // the rules' advising directory: "Not sure who to ask?"
};
export type ImportResult = {
  catalog_year: string;
  profile: Profile;
  remaining: unknown;
  cross_check: string[];
  warnings: string[];
  see_advisor: Advisor[];
  not_used?: Taken[];
  notes_by_group?: Record<string, string[]>;
  warnings_by_group?: Record<string, string[]>;
};
export type Program = { id: string; title: string };
export type Course = {
  code: string;
  title: string;
  units_min: number;
  units_max: number;
  description: string | null;
  source_page: number;
  prereq?: { raw_text?: string } | null;
  offered_terms?: Offered | null;
  close_matches?: string[];
};
export type Offered = {
  fall?: number[];
  spring?: number[];
  summer?: number[];
  last?: string;
  online_only?: string[];
};

export type Pace = {
  terms: number;
  load: string;
  planned_units: number;
  normal_load?: { max_units_per_term: number; terms: number; est_graduation_term: string; note: string };
  fold_last_term?: { term: string; units: number; terms: number; est_graduation_term: string; note: string };
  min_terms_by_prereqs: number;
  min_terms_by_units: number;
  longest_chain: string[];
  graduate_by?: string;
  on_time?: boolean;
  why_not?: string[];
};
export type PlanError = { error?: string; message: string; term?: string; group?: string };
export type Checked = {
  valid: boolean;
  errors: PlanError[];
  warnings?: string[];
  see_advisor?: Advisor[];
  courses?: Record<string, CourseInfo>;
};
export type PlanResult = {
  semesters: Semester[];
  needs_input?: string;
  est_graduation_term?: string;
  pace?: Pace;
  warnings: string[];
  see_advisor?: Advisor[];
  check?: Checked;
  courses?: Record<string, CourseInfo>;
};

export type ChatMessage = { role: "user" | "assistant"; content: string };
export type Pick = {
  group: string;
  term: string;
  code: string;
  readiness?: string;
  covers: string[];
  online?: boolean;
  ai?: boolean; // the page's own note: the AI helper chose it (the server ignores it)
};
export type Assisted = {
  reply: string;
  changed: boolean;
  semesters: Semester[];
  picks: Pick[];
  check: Checked;
  rebuilt: PlanResult | null; // the chat changed the pace: a new plan, with its own dates
  options: Partial<Profile>; // what the chat changed about the student, the record included
  left?: Left; // AI questions left this hour and today
  sections: Record<string, string[]>; // {term: class numbers} the student chose for the Schedule, the chat's too
};
export type Option = {
  code: string;
  title: string;
  units: number;
  source_page: number;
  readiness: "ready" | "check" | "blocked";
  also_covers: string[];
  offered?: Offered | null;
  description?: string | null;
  note?: string;
  cannot_check?: string[];
  blocked_by?: string[];
  ready_by?: string;
  not_offered?: string;
};
export type Electives = {
  title: string;
  by_term: string;
  source: string;
  units_needed?: number;
  min_units_from?: { subject: string; units: number; done: number };
  approval?: string;
  options: Option[];
  total_options: number;
  warnings: string[];
};
export type Meeting = { days?: string; time?: string; where?: string };
export type Section = {
  section: string;
  component: string;
  mode: string;
  class_nbr: string;
  meetings: Meeting[];
  instructor?: string;
  seats_open?: number;
  waitlist_open?: number;
  rate_my_professors?: Record<string, string>;
  clashes_with?: string[];
};
export type Sections = {
  term: string;
  sections: Record<string, Section[]>;
  schedule: Record<string, string[]> | null;
  sets: number;
  all_counted: boolean;
  pinned_blocking: boolean;
  always_clash: string[][];
  not_offered: string[];
  unknown: string[];
  scraped_at: string | null;
  warnings: string[];
};

export type Choice = { id: string; title: string };
export class EngineError extends Error {
  constructor(
    text: string,
    readonly code: string,
    readonly choices: Choice[] = [], // unknown_program on a DPR: the programs it could be
  ) {
    super(text);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error("We couldn’t reach GatorPath. Check that it’s running, then try again.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      typeof body?.detail === "string" ? body.detail : "Something went wrong on our side. Try again.",
    );
  }
  if (body?.error)
    throw new EngineError(body.warnings?.join(" ") || String(body.error), String(body.error), body.choices);
  return body;
}

const post = <T,>(path: string, body: unknown) =>
  call<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const message = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong. Try again.");

export function importDpr(file: File, program?: string) {
  const form = new FormData();
  form.append("file", file);
  if (program) form.append("program", program); // the student's pick when the DPR alone doesn't say
  return call<ImportResult>("/api/import-dpr", { method: "POST", body: form });
}
export const getAudit = (profile: Profile) => post<Audit>("/api/audit", { profile });

let programs: Promise<Program[]> | undefined;
export function getPrograms() {
  programs ??= call<{ programs: Program[] }>("/api/programs").then((r) => r.programs);
  programs.catch(() => (programs = undefined)); // a failed call can be retried
  return programs;
}
export type Pathway = { pathway: string; courses: { code: string; title: string }[] };
export const getPathways = (program: string, catalogYear?: string) =>
  call<{ pathways: Pathway[] }>(
    `/api/pathways?program=${encodeURIComponent(program)}${catalogYear ? `&catalog_year=${encodeURIComponent(catalogYear)}` : ""}`,
  ).then((r) => r.pathways);
export const getAiStatus = () => call<{ connected: boolean }>("/api/ai-status");
export const getCourse = (code: string) => call<Course>(`/api/course?code=${encodeURIComponent(code)}`);
export type CourseMatch = { code: string; title: string; description: string | null };
export const searchCourses = (query: string) =>
  call<{ results: CourseMatch[] }>(`/api/search-courses?query=${encodeURIComponent(query)}`).then((r) => r.results);
export const buildPlan = (profile: Profile, options: Options) =>
  post<PlanResult>("/api/plan", { profile, options });
export const checkPlan = (profile: Profile, plan: Plan) =>
  post<Checked>("/api/check", { profile, plan });
export const getElectives = (profile: Profile, requirement: string, plan: Plan, by_term: string, query = "") =>
  post<Electives>("/api/electives", { profile, requirement, plan, by_term, limit: 100, query });
export function getSections(term: string, courses: string[], online: string[], keep: string[] = []) {
  const query = new URLSearchParams({ term });
  courses.forEach((c) => query.append("courses", c));
  online.forEach((c) => query.append("online", c));
  keep.forEach((n) => query.append("keep", n)); // sections the student chose: the rest fit around them
  return call<Sections>(`/api/sections?${query}`);
}
/** The AI helper: a chat message, or with none, fills the plan. check_plan decides every change on the server. */
export const assist = (
  profile: Profile,
  semesters: Semester[],
  picks: Pick[],
  messages: ChatMessage[],
  sections: Record<string, string[]>,
  notes: string[] = [], // what the DPR import found: the first reply says it
) => post<Assisted>("/api/assist", { profile, plan: { semesters }, picks, messages, sections, notes });
