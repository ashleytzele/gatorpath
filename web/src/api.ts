// The server's fields as the engine returns them. Nothing here is kept: a student's record lives in this tab's memory.
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
export type Profile = Options & {
  program: string;
  catalog_year?: string;
  completed?: Taken[];
  in_progress?: string[];
  gpa?: number;
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
  quote?: string;
  min_units_from?: { subject: string; units: number; done: number };
};
export type Total = { value: number; needed?: number; max?: number; ok: boolean };
export type Audit = {
  catalog_year: string;
  program: string;
  complete: boolean;
  groups: Group[];
  totals: Record<string, Total> & { units_in_progress: number };
  warnings: string[];
  see_advisor: Advisor[];
  courses: Record<string, CourseInfo>;
};
export type ImportResult = {
  catalog_year: string;
  profile: Profile;
  remaining: unknown;
  cross_check: string[];
  warnings: string[];
  see_advisor: Advisor[];
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
export type PlanError = { error?: string; message: string; term?: string };
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

class EngineError extends Error {}

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
  if (body?.error) throw new EngineError(body.warnings?.join(" ") || String(body.error));
  return body;
}

const post = <T,>(path: string, body: unknown) =>
  call<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const message = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong. Try again.");

export function importDpr(file: File) {
  const form = new FormData();
  form.append("file", file);
  return call<ImportResult>("/api/import-dpr", { method: "POST", body: form });
}
export const getAudit = (profile: Profile) => post<Audit>("/api/audit", { profile });

let programs: Promise<Program[]> | undefined;
export function getPrograms() {
  programs ??= call<{ programs: Program[] }>("/api/programs").then((r) => r.programs);
  programs.catch(() => (programs = undefined)); // a failed call can be retried
  return programs;
}
export const getCourse = (code: string) => call<Course>(`/api/course?code=${encodeURIComponent(code)}`);
export const buildPlan = (profile: Profile, options: Options) =>
  post<PlanResult>("/api/plan", { profile, options });
export const checkPlan = (profile: Profile, plan: Plan) =>
  post<Checked>("/api/check", { profile, plan });
