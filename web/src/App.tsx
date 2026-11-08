import { useEffect, useRef, useState } from "react";
import {
  assist,
  buildPlan,
  checkPlan,
  EngineError,
  type Choice,
  getAudit,
  getCourse,
  getElectives,
  getPrograms,
  getSections,
  importDpr,
  message,
  type Advisor,
  type Assisted,
  type Audit,
  type ChatMessage,
  type Checked,
  type CourseInfo,
  type Group,
  type ImportResult,
  type Meeting,
  type Offered,
  type Option,
  type Options,
  type Pick,
  type PlanError,
  type PlanResult,
  type Profile,
  type Section,
  type Semester,
  type Slot,
  type Taken,
} from "./api";
import { Landing } from "./Landing";
import { RecordEditor, RecordScreen } from "./Record";
import { termLabel } from "./logic";
import {
  ASK_ADVISOR, Button, DEMO, ErrorCard, Footer, Header, Icon, type IconName, Loading, Logo, NAVIGATOR,
  Stepper, StatusBadge, Tooltip, nearbyTerms, plainText, useLoad, type Screen,
} from "./ui";

type Tab = "plan" | "progress" | "electives" | "schedule";

function AdvisingNote() {
  return (
    <aside className="advising-note" aria-label="Advising">
      <Icon name="info" />
      <p>
        <b>GatorPath is a planning guide.</b> For any question about your plan, talk to an advisor
        before you register.
      </p>
      <a href={NAVIGATOR} target="_blank" rel="noreferrer">
        {ASK_ADVISOR} <Icon name="arrow" size={14} />
      </a>
    </aside>
  );
}

const NOT_ON_DPR = "not on the student's DPR"; // the engine's waived_by for a requirement the student left out
const isDone = (g: Group) => g.status === "satisfied" || g.status === "waived";
const universityGroups = (audit: Audit) => audit.groups.filter((g) => g.kind === "university");

/** GE and university rows. Without a plan (Review, from the DPR) they use the DPR's words: Completed, Incomplete. */
/** Areas the DPR doesn't list (D33): left out on import, and the student can put one back or leave it out again. */
type DprMissing = { missing: string[]; left: string[]; set: (ids: string[], leave: boolean) => void };

function GeRequirementRows({
  groups,
  plannedIn,
  dpr,
}: {
  groups: Group[];
  plannedIn?: (group: Group) => string | undefined;
  dpr?: DprMissing;
}) {
  const record = !plannedIn;
  const askable = groups.filter((g) => dpr?.missing.includes(g.id)).map((g) => g.id);
  const out = askable.filter((id) => dpr?.left.includes(id));
  const [they, them] = askable.length === 1 ? ["it’s", "it"] : ["they’re", "them"];
  return (
    <div className="shared-ge-rows progress">
      {!!askable.length && dpr && (
        <div className="dpr-missing-note">
          <Icon name="info" size={15} />
          <p>
            {askable.length === 1 ? "One of these isn’t" : `${askable.length} of these aren’t`} on your DPR,
            {out.length
              ? ` so ${they} left out of your plan. Confirm with an advisor that you don’t need ${them}.`
              : ` but ${they} back in your plan.`}
          </p>
          <button className="let-pick" onClick={() => dpr.set(askable, !out.length)}>
            {out.length ? "Put them back in my plan" : "Leave them out"}
          </button>
        </div>
      )}
      {[...groups.filter((g) => askable.includes(g.id)), ...groups.filter((g) => !askable.includes(g.id))].map((g) => {
        const planned = plannedIn?.(g);
        const done = isDone(g);
        const leftOut = g.waived_by === NOT_ON_DPR;
        return (
          <div className="shared-ge-row" key={g.id}>
            <div className="ge-area-name" title={`Bulletin ${g.source}`}>
              <b>{g.title}</b>
            </div>
            <StatusBadge
              type={leftOut ? "warning" : done ? "done" : g.in_progress.length ? "progress" : planned ? "planned" : "remaining"}
            >
              {leftOut
                ? "Not on your DPR"
                : done
                  ? record ? "Completed" : "Done"
                  : g.in_progress.length
                    ? "In progress"
                    : planned
                      ? "Planned"
                      : record ? "Incomplete" : "Remaining"}
            </StatusBadge>
            <p>{[...g.counted, ...g.in_progress].join(", ") || planned || "—"}</p>
          </div>
        );
      })}
    </div>
  );
}

function ReviewScreen({
  profile,
  imported,
  edit,
  next,
}: {
  profile: Profile;
  imported: ImportResult | null;
  edit: (profile: Profile) => void;
  next: () => void;
}) {
  const audit = useLoad(() => getAudit(profile), [profile]);
  const programs = useLoad(getPrograms, []);
  const body = () => {
    if (audit.error) return <ErrorCard text={audit.error} retry={audit.retry} />;
    if (!audit.data) return <Loading label="Checking your record against the Bulletin…" />;
    const a = audit.data;
    const t = a.totals;
    const left = profile.not_on_dpr ?? [];
    const notFound = imported?.cross_check.find((line) => line.startsWith("Not found on this DPR")) ?? "";
    const dpr: DprMissing = {
      missing: a.groups.filter((g) => notFound.includes(g.title)).map((g) => g.id),
      left,
      set: (ids, leave) =>
        edit({ ...profile, not_on_dpr: leave ? [...new Set([...left, ...ids])] : left.filter((x) => !ids.includes(x)) }),
    };
    const met = a.groups.filter(isDone).length;
    const going = a.groups.filter((g) => !isDone(g) && g.in_progress.length).length;
    const gpa = profile.gpa ?? t.gpa_sf_state?.value; // the DPR's, when there is one
    return (
      <>
        <div className="dash-tiles">
          <div className="dash-tile wide">
            <small>Major</small>
            <b className="text">{programs.data?.find((p) => p.id === profile.program)?.title ?? profile.program}</b>
          </div>
          <div className="dash-tile">
            <small>
              Catalog year <Tooltip text="The Bulletin year whose degree rules apply to you." />
            </small>
            <b className="text">{profile.catalog_year ?? a.catalog_year}</b>
          </div>
          {(
            [
              ["Units", t.units.value, t.units_in_progress, t.units.needed ?? 120],
              ["Upper-division units", t.upper_division_units.value, t.upper_division_units_in_progress ?? 0,
               t.upper_division_units.needed ?? 0],
              ["Requirements completed", met, going, a.groups.length],
            ] as [string, number, number, number][]
          ).map(([label, value, more, of]) => {
            const units = label !== "Requirements completed"; // units count in progress, as the DPR's "taken" does
            return (
              <div className="dash-tile" key={label}>
                <small>{label}</small>
                <b>
                  {units ? value + more : value} <span>/ {of}</span>
                </b>
                <UnitTrack value={value} going={more} total={of} label={label} />
                {!!more && <em className="going-note">{units ? `incl. ${more}` : `+${more}`} in progress</em>}
              </div>
            );
          })}
          {!!gpa && (
            <div className="dash-tile">
              <small>GPA</small>
              <b>{gpa}</b>
            </div>
          )}
        </div>
        <div className="dash-grid">
          <div className="dash-main">
            <DegreeProgress audit={a} bars={false} dpr={dpr} />
          </div>
          <aside className="dash-side">
            <RecordEditor profile={profile} titles={a.courses} edit={edit} />
            <Button onClick={next}>
              Looks right <Icon name="arrow" />
            </Button>
          </aside>
        </div>
      </>
    );
  };
  return (
    <main className="flow-page wide dash">
      <Stepper current={1} />
      <div className="flow-heading">
        <h1>Does this look right?</h1>
        <p>
          {imported ? "This is what your DPR shows." : "This is what you told us."} Fix a grade, or add a
          course it doesn’t show. Your DPR is the official record.
        </p>
      </div>
      {body()}
    </main>
  );
}

function SectionCard({
  title,
  count,
  children,
  className = "",
}: {
  title: string;
  count?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`section-card ${className}`}>
      <div className="section-card-head">
        <h2>{title}</h2>
        {count && <span>{count}</span>}
      </div>
      {children}
    </section>
  );
}
function CourseMini({ code, title, status }: { code: string; title: string; status: string }) {
  return (
    <div className="course-mini">
      <div>
        <b>{code}</b>
        <small>{title}</small>
      </div>
      <StatusBadge type="progress">{status}</StatusBadge>
    </div>
  );
}

const GOALS: Record<string, string[] | null> = {
  "bs-cs": [
    "AI / Machine Learning",
    "Cybersecurity",
    "Web Development",
    "Game Development",
    "Data Science",
    "Systems",
  ],
  "ba-psychology": ["Clinical / Counseling", "Research", "Developmental", "Industrial-Organizational"],
};
const PREVIEW_MAJORS = ["bs-cs", "ba-psychology", "ba-history", "bs-environmental-studies"];

function GoalsScreen({
  profile,
  saved,
  needs,
  build,
}: {
  profile: Profile;
  saved: Options;
  needs?: string;
  build: (options: Options) => void;
}) {
  const [goal, setGoal] = useState(saved.goal ?? "");
  const [advanced, setAdvanced] = useState(false);
  const [previewMajor, setPreviewMajor] = useState(profile.program);
  const [graduateBy, setGraduateBy] = useState(saved.graduate_by ?? "");
  const [f1, setF1] = useState(saved.f1);
  const [qr, setQr] = useState(saved.qr_pathway ?? profile.qr_pathway);
  const [start, setStart] = useState(saved.start_term ?? "");
  const [summer, setSummer] = useState(saved.include_summer ?? false);
  const [winter, setWinter] = useState(saved.include_winter ?? false);
  const [maxUnits, setMaxUnits] = useState(saved.max_units_per_term);
  const major = DEMO ? previewMajor : profile.program;
  const goals = major === "bs-environmental-studies" ? null : (GOALS[major] ?? []);
  const hasElectives = goals !== null;
  const brandNew = !profile.completed?.length && !profile.in_progress?.length;
  const askQr = !profile.qr_pathway && (brandNew || needs === "qr_pathway");
  const programs = useLoad(getPrograms, []);
  const title = programs.data?.find((p) => p.id === major)?.title ?? major;
  return (
    <main className="flow-page goals-page">
      <Stepper current={2} />
      <div className="flow-heading">
        <h1>What matters to you?</h1>
        <p>Your dates and load set your pace. Your focus shapes the courses we choose for you.</p>
      </div>
      {needs && (
        <div className="error-card" role="alert">
          <Icon name="warning" />
          <div>
            <b>
              {needs === "qr_pathway"
                ? "We need your math placement to place your first math class."
                : "We need your first term to start your plan."}
            </b>
            <p>
              Not sure?{" "}
              <a href={NAVIGATOR} target="_blank" rel="noreferrer">
                Ask an advisor in Navigator
              </a>
            </p>
          </div>
        </div>
      )}
      <div className="major-context">
        <span>
          <Icon name="book" /> Goals for {DEMO ? "" : title}
        </span>
        {DEMO && (
          <select
            value={previewMajor}
            onChange={(event) => {
              setPreviewMajor(event.target.value);
              setGoal("");
            }}
            aria-label="Preview goal options for major"
          >
            {[...new Set([profile.program, ...PREVIEW_MAJORS])].map((id) => (
              <option key={id}>{id}</option>
            ))}
          </select>
        )}
      </div>
      {hasElectives && (
        <div className="question-block">
          <div className="question-title">
            <span>1</span>
            <div>
              <h2>
                {goals.length ? "What do you want to focus on?" : "What are you interested in?"}
              </h2>
              <p>We’ll choose your electives around it. You can change any of them.</p>
            </div>
          </div>
          {goals.length > 0 ? (
            <div className="choice-chips">
              {goals.map((x) => (
                <button className={goal === x ? "selected" : ""} onClick={() => setGoal(x)} key={x}>
                  {goal === x && <Icon name="check" size={14} />}
                  {x}
                </button>
              ))}
            </div>
          ) : (
            <input
              className="interest-input"
              placeholder="What are you interested in?"
              value={goal === "Undecided" ? "" : goal}
              onChange={(e) => setGoal(e.target.value)}
            />
          )}
          <button
            className={`undecided-choice ${goal === "Undecided" ? "selected" : ""}`}
            onClick={() => setGoal("Undecided")}
          >
            {goal === "Undecided" && <Icon name="check" size={14} />} Undecided
          </button>
        </div>
      )}
      {!hasElectives && (
        <div className="no-goals-note">
          <Icon name="check" />
          <div>
            <b>No focus question needed for {title}</b>
            <span>This major has no elective choices, so we’ll skip this step.</span>
          </div>
        </div>
      )}
      <div className="question-grid">
        <div className="question-block">
          <div className="question-title">
            <span>2</span>
            <div>
              <h2>When do you want to graduate?</h2>
              <p>We’ll tell you if that pace looks realistic.</p>
            </div>
          </div>
          <select
            aria-label="When do you want to graduate?"
            value={graduateBy}
            onChange={(e) => setGraduateBy(e.target.value)}
          >
            <option value="">Just follow the recommended pace</option>
            {nearbyTerms(0, 12).map((t) => (
              <option value={t} key={t}>
                {termLabel(t)}
              </option>
            ))}
          </select>
        </div>
        <div className="question-block">
          <div className="question-title">
            <span>3</span>
            <div>
              <h2>
                Are you on an F-1 student visa?{" "}
                <Tooltip text="F-1 students need at least 12 units every fall and spring." />
              </h2>
              <p>This affects your minimum course load.</p>
            </div>
          </div>
          <div className="segmented">
            <button className={f1 === false ? "active" : ""} onClick={() => setF1(false)}>
              No
            </button>
            <button className={f1 === true ? "active" : ""} onClick={() => setF1(true)}>
              Yes
            </button>
            <button className={f1 === undefined ? "active" : ""} onClick={() => setF1(undefined)}>
              Prefer not to say
            </button>
          </div>
        </div>
      </div>
      {askQr && (
        <div className="question-block compact-question">
          <div className="question-title">
            <span>4</span>
            <div>
              <h2>What is your math placement QR?</h2>
              <p>We use this to place your first math class.</p>
            </div>
          </div>
          <div className="segmented small">
            <button className={qr === "1/2" ? "active" : ""} onClick={() => setQr("1/2")}>
              QR 1 / 2
            </button>
            <button className={qr === "3/4" ? "active" : ""} onClick={() => setQr("3/4")}>
              QR 3 / 4
            </button>
            <button className={qr === undefined ? "active" : ""} onClick={() => setQr(undefined)}>
              I’m not sure
            </button>
          </div>
        </div>
      )}
      {needs === "start_term" && (
        <div className="question-block compact-question">
          <div className="question-title">
            <span>5</span>
            <div>
              <h2>What’s your first term?</h2>
              <p>Your plan starts here.</p>
            </div>
          </div>
          <select aria-label="First term" value={start} onChange={(e) => setStart(e.target.value)}>
            <option value="">Choose a term</option>
            {nearbyTerms(0, 4).map((t) => (
              <option value={t} key={t}>
                {termLabel(t)}
              </option>
            ))}
          </select>
        </div>
      )}
      <button className="advanced-toggle" onClick={() => setAdvanced(!advanced)}>
        <span>
          <Icon name="plus" /> Advanced options
        </span>
        <Icon name="chevron" />
      </button>
      {advanced && (
        <div className="advanced-panel">
          <label>
            <input type="checkbox" checked={summer} onChange={(e) => setSummer(e.target.checked)} />{" "}
            Include summer terms
          </label>
          <label>
            <input type="checkbox" checked={winter} onChange={(e) => setWinter(e.target.checked)} />{" "}
            Include Winter Session
          </label>
          <label>
            Maximum units per term: {maxUnits ?? "the roadmap’s pace"}{" "}
            <input
              type="range"
              min="12"
              max="19"
              value={maxUnits ?? 15}
              onChange={(e) => setMaxUnits(Number(e.target.value))}
            />
            <small>Above the roadmap’s load needs advisor approval.</small>
          </label>
        </div>
      )}
      <div className="flow-action">
        <span>
          <Icon name="lock" /> You can change these later.
        </span>
        <Button
          onClick={() =>
            build({
              ...(goal && { goal }),
              ...(graduateBy && { graduate_by: graduateBy }),
              ...(f1 !== undefined && { f1 }),
              ...(qr && { qr_pathway: qr }),
              ...(start && { start_term: start }),
              ...(summer && { include_summer: true }),
              ...(winter && { include_winter: true }),
              ...(maxUnits !== undefined && { max_units_per_term: maxUnits }),
            })
          }
        >
          Build my plan <Icon name="arrow" />
        </Button>
      </div>
    </main>
  );
}

function BuildingScreen({
  profile,
  options,
  done,
  back,
}: {
  profile: Profile;
  options: Options;
  done: (plan: PlanResult, audit: Audit) => void;
  back: () => void;
}) {
  const built = useLoad(
    () => Promise.all([buildPlan(profile, options), getAudit({ ...profile, ...options })]),
    [],
  );
  useEffect(() => {
    if (built.data) done(...built.data);
  }, [built.data]); // eslint-disable-line react-hooks/exhaustive-deps
  if (built.error) {
    return (
      <main className="flow-page">
        <ErrorCard text={built.error} retry={built.retry} />
        <div className="flow-action">
          <Button kind="secondary" onClick={back}>
            Back to your goals
          </Button>
        </div>
      </main>
    );
  }
  return (
    <main className="building-screen" role="status">
      <div className="building-orb">
        <Icon name="route" size={32} />
        <i />
        <i />
        <i />
      </div>
      <h1>Building your plan from the Bulletin…</h1>
      <p>Ordering prerequisites, balancing units, and checking course availability.</p>
      <div className="check-list">
        <span>
          <Icon name="check" /> Your record is in
        </span>
        <span className="checking">
          <i /> Mapping requirements and building semesters
        </span>
      </div>
      <div className="skeleton-row">
        <i />
        <i />
        <i />
      </div>
    </main>
  );
}

const isSlot = (c: string | Slot): c is Slot => typeof c !== "string";
const yearOf = (term: string) => {
  const year = Number(term.slice(0, 4));
  const first = term.endsWith("fall") ? year : year - 1;
  return `${first}–${String(first + 1).slice(2)}`;
};
const unitsOf = (c: string | Slot, info: Record<string, CourseInfo>) =>
  isSlot(c) ? c.units : parseFloat(String(info[c]?.units)) || 0;
const termUnits = (s: Semester, info: Record<string, CourseInfo>) =>
  s.courses.reduce((total, c) => total + unitsOf(c, info), 0);
const unitText = (units?: number | string) => `${units} ${Number(units) === 1 ? "unit" : "units"}`;
/** What a class in the plan is for: what it was picked for, or the requirement that lists it. */
function countsFor(code: string, picks: Pick[], audit: Audit) {
  const group = picks.find((p) => p.code === code)?.group;
  if (group === "elective") return "Free elective";
  return audit.groups.find(
    (g) => g.id === group || [...(g.remaining ?? []), ...g.in_progress].includes(code),
  )?.title;
}
const slotLabel = (slot: Slot, audit: Audit) =>
  slot.slot === "elective"
    ? "Free elective: any course"
    : (audit.groups.find((g) => g.id === slot.slot)?.title ?? slot.slot);

/** A slot of the plan to fill, or a pick to change. */
type Target = { group: string; term: string; title: string; replacing?: string };

/** One plan and what's known about it, shared by the tabs. It lives in memory only. */
type Work = {
  student: Profile;
  options: Options;
  audit: Audit;
  plan: PlanResult;
  semesters: Semester[];
  check: Checked;
  info: Record<string, CourseInfo>;
  picks: Pick[];
  busy: string;
  failed: string;
  whatIf: (change: Options, label: string) => void;
  applyFold: () => void;
  fill: () => void;
  aiDown: boolean;
  sections: Record<string, string[]>; // {term: class numbers} the student chose
  setSections: (term: string, keep: string[]) => void;
  aiBusy: boolean; // the chat's answer replaces the plan, so a section chosen meanwhile would be lost
  ask: (text: string) => void; // sends a message to the chat, as if the student typed it
};

function Tabs({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  const items: [Tab, string, IconName, string][] = [
    ["plan", "Plan", "route", "Plan"],
    ["progress", "Progress", "check", "Progress"],
    ["electives", "Electives & GE", "book", "Electives"],
    ["schedule", "Schedule", "calendar", "Schedule"],
  ];
  return (
    <nav className="app-tabs" aria-label="Your plan">
      {items.map(([key, label, icon, short]) => (
        <button
          key={key}
          className={tab === key ? "active" : ""}
          aria-current={tab === key ? "page" : undefined}
          onClick={() => setTab(key)}
        >
          <Icon name={icon} />
          <span className="long-label">{label}</span>
          <span className="short-label">{short}</span>
        </button>
      ))}
    </nav>
  );
}

/** "Stopped at 2030-spring: nothing more can be scheduled. Blocked: A; B; slots waiting: ids" as one line per course. */
function problemLines(message: string, audit: Audit): string[] {
  const stopped = message.match(/^Stopped at (\S+): nothing more can be scheduled\. Blocked: (.*)$/s);
  if (!stopped) return [plainText(message, audit)];
  return [
    `Nothing more fits from ${termLabel(stopped[1])} on:`,
    ...stopped[2].split("; ").map((part) =>
      part.startsWith("slots waiting: ")
        ? `Still to choose: ${part.slice(15).split(", ").map((id) => plainText(id, audit)).join(", ")}`
        : plainText(part, audit),
    ),
  ];
}

/** What stops the plan, one line each in the student's words; any line can go to the chat to fix. */
function ProblemPanel({ errors, audit, ask }: { errors: PlanError[]; audit: Audit; ask?: (text: string) => void }) {
  const [all, setAll] = useState(false);
  const lines = [...new Set(errors.flatMap((e) => problemLines(e.message, audit)))];
  const count = lines.filter((l) => !l.endsWith(":")).length;
  return (
    <div className="plan-problem-panel" role="alert">
      <div>
        <Icon name="warning" />
        <span>
          <b>{count === 1 ? "One thing stops this plan" : `${count} things stop this plan`}</b>
          <small>Ask GatorPath to fix one, or ask an advisor what to do.</small>
        </span>
      </div>
      {(all ? lines : lines.slice(0, 6)).map((line) =>
        line.endsWith(":") ? (
          <h3 className="problem-lead" key={line}>
            {line}
          </h3>
        ) : (
          <p key={line}>
            <span>{line}</span>
            {ask && <button onClick={() => ask(`Fix this in my plan: ${line}`)}>Ask GatorPath</button>}
          </p>
        ),
      )}
      {lines.length > 6 && (
        <button className="let-pick problem-more" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${count}`}
        </button>
      )}
    </div>
  );
}

function AdvisorCards({ items, audit }: { items: Advisor[]; audit: Audit }) {
  return (
    <div className="advisor-list">
      {items.map((a) => (
        <div key={a.role}>
          <b>{a.who}</b>
          <p>{plainText(`${a.why.join(" ")} ${a.how_to_book ?? ""}`, audit)}</p>
          <a href={NAVIGATOR} target="_blank" rel="noreferrer">
            {ASK_ADVISOR} <Icon name="arrow" size={12} />
          </a>
        </div>
      ))}
    </div>
  );
}

function PlanView({
  work,
  openChoice,
  openCourse,
  openSchedule,
  toast,
}: {
  work: Work;
  openChoice: (slot: Slot, term: string) => void;
  openCourse: (code: string) => void;
  openSchedule: () => void;
  toast: (x: string) => void;
}) {
  const { audit, check, info, options, plan, semesters } = work;
  const pace = plan.pace;
  const [preview, setPreview] = useState<"" | "open" | "complete" | "problem" | "unreachable">("");
  const slots = semesters.flatMap((s) => s.courses.filter(isSlot).map((slot) => ({ slot, term: s.term })));
  const choicesLeft = slots.length;
  const unitsLeft = semesters.reduce((total, s) => total + termUnits(s, info), 0);
  const years = [...new Set(semesters.map((s) => yearOf(s.term)))];
  const lastTerm = semesters[semesters.length - 1]?.term;
  const graduation = lastTerm; // the plan as it stands: a chat or a pick can move it past build_plan's estimate
  const unreachable = pace?.on_time === false && !!pace.why_not?.length;
  const planState =
    preview || (!check.valid ? "problem" : unreachable ? "unreachable" : choicesLeft ? "open" : "complete");
  // "Stopped at …" says why the plan can't finish: the errors are only what that left uncovered
  const stopped = plan.warnings.filter((w) => w.startsWith("Stopped at")).map((w) => ({ message: w }));
  const found = [...stopped, ...check.errors];
  const errors = found.length ? found : [{ message: "Sample problem, from the preview bar." }];
  const warnings = [...new Set([...plan.warnings, ...(check.warnings ?? [])])].filter(
    (w) => !w.startsWith("Stopped at"),
  );
  const advisors = [...(check.see_advisor ?? []), ...(plan.see_advisor ?? [])].filter(
    (a, i, all) => all.findIndex((x) => x.role === a.role) === i,
  );
  const chain = pace?.longest_chain ?? [];
  return (
    <div className="app-content">
      {DEMO && (
        <div className="variant-switcher">
          <span>Preview plan state</span>
          {[
            ["open", "Choices open"],
            ["complete", "All choices made"],
            ["problem", "Has a problem"],
            ["unreachable", "Date unreachable"],
          ].map(([value, label]) => (
            <button
              className={planState === value ? "active" : ""}
              onClick={() => setPreview(value as typeof preview)}
              key={value}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      {work.busy && (
        <div className="plan-status open" role="status">
          <span>
            <Icon name="spark" /> <b>{work.busy}</b> Your plan below is already real, and this can take a
            minute or two.
          </span>
        </div>
      )}
      {planState === "open" && !work.busy && (
        <div className="plan-status open">
          <span>
            <Icon name="clock" /> <b>{choicesLeft} choices left in your plan</b>
          </span>
          <span className="plan-status-actions">
            <button onClick={work.fill}>
              Fill them with AI <Icon name="spark" size={14} />
            </button>
            {work.aiDown && (
              <button
                onClick={() =>
                  document.getElementById("first-open-slot")?.scrollIntoView({ behavior: "smooth" })
                }
              >
                Choose myself <Icon name="arrow" size={14} />
              </button>
            )}
          </span>
        </div>
      )}
      {planState === "complete" && (
        <div className="plan-status complete">
          <span>
            <Icon name="check" /> <b>All choices made.</b> Take this plan to an advisor to confirm
            it before you register.
          </span>
          <a href={NAVIGATOR} target="_blank" rel="noreferrer">
            {ASK_ADVISOR} <Icon name="arrow" size={14} />
          </a>
        </div>
      )}
      {planState === "problem" && <ProblemPanel errors={errors} audit={audit} ask={work.ask} />}
      {planState === "unreachable" && (
        <div className="plan-problem-panel unreachable">
          <div>
            <Icon name="clock" />
            <span>
              <b>{termLabel(pace?.graduate_by) || "That date"} isn’t reachable</b>
              <small>{plainText(pace?.why_not?.join(" ") ?? "", audit)}</small>
            </span>
          </div>
          <div className="problem-actions">
            <Button
              kind="secondary"
              onClick={() => work.whatIf({ include_summer: true }, "With summers")}
            >
              Add summer terms
            </Button>
            <a className="button secondary" href={NAVIGATOR} target="_blank" rel="noreferrer">
              Ask an advisor in Navigator
            </a>
          </div>
        </div>
      )}
      <section className="plan-hero">
        <div>
          {planState === "problem" ? (
            <>
              <h1>
                You could graduate <em>{termLabel(graduation)}</em>
              </h1>
              <p className="hero-note">Once the problems above are fixed. Until then the date isn’t certain.</p>
            </>
          ) : (
            <h1>
              You can graduate <em>{termLabel(graduation)}</em>
            </h1>
          )}
          <div className="hero-badges">
            <StatusBadge type={choicesLeft ? "warning" : "done"}>
              {choicesLeft ? `${choicesLeft} choices left` : "All choices made"}
            </StatusBadge>
            <span>{semesters.length} semesters left</span>
            <span>{unitsLeft} units left</span>
          </div>
          {(pace?.normal_load || pace?.fold_last_term) && (
            <div className="pace-options">
              {pace.normal_load && (
                <button
                  onClick={() =>
                    work.whatIf(
                      { max_units_per_term: pace.normal_load!.max_units_per_term },
                      "At a lighter pace",
                    )
                  }
                >
                  <b>Lighter</b>
                  <span>
                    Keep every term at {pace.normal_load.max_units_per_term} units or less · graduate{" "}
                    {termLabel(pace.normal_load.est_graduation_term)}
                  </span>
                </button>
              )}
              {pace.fold_last_term && (
                <button onClick={work.applyFold}>
                  <b>Faster</b>
                  <span>
                    One {pace.fold_last_term.units}-unit {termLabel(pace.fold_last_term.term)} · graduate{" "}
                    {termLabel(pace.fold_last_term.est_graduation_term)}
                  </span>
                </button>
              )}
            </div>
          )}
        </div>
        {pace && (
          <div className="pace-note">
            <span>
              <Icon name="route" />
            </span>
            {pace.min_terms_by_prereqs >= pace.min_terms_by_units && chain.length > 0 ? (
              <p>
                Your longest prerequisite chain{" "}
                <Tooltip text="A prerequisite is a class you must finish before taking another." />{" "}
                <b>{chain.join(" → ")}</b> sets your graduation date.
              </p>
            ) : (
              <p>
                Your units per term set your graduation date: you need at least{" "}
                <b>{pace.min_terms_by_units} terms</b> at this pace.
              </p>
            )}
          </div>
        )}
      </section>
      <ol className="plan-route" aria-label="Route to graduation">
        {semesters.map((s, i) => (
          <li key={s.term} className={i === 0 ? "next" : i === semesters.length - 1 ? "finish" : ""}>
            <span className="route-dot" aria-hidden="true">
              {i === semesters.length - 1 && <Icon name="check" size={12} />}
            </span>
            <small>
              {termLabel(s.term).split(" ")[0]} ’{s.term.slice(2, 4)}
            </small>
          </li>
        ))}
      </ol>
      <section className="what-if">
        <div>
          <span>What if I…</span>
          <button
            className={options.include_summer ? "active" : ""}
            disabled={!!work.busy}
            onClick={() =>
              work.whatIf(
                { include_summer: !options.include_summer },
                options.include_summer ? "Without summers" : "With summers",
              )
            }
          >
            <Icon name="plus" /> Add summer
          </button>
          <button
            className={options.include_winter ? "active" : ""}
            disabled={!!work.busy}
            onClick={() =>
              work.whatIf(
                { include_winter: !options.include_winter },
                options.include_winter ? "Without Winter Session" : "With Winter Session",
              )
            }
          >
            <Icon name="plus" /> Add winter
          </button>
          <label>
            Units per term{" "}
            <select
              disabled={!!work.busy}
              value={options.max_units_per_term ?? ""}
              onChange={(e) =>
                work.whatIf(
                  { max_units_per_term: e.target.value ? Number(e.target.value) : undefined },
                  e.target.value ? `At ${e.target.value} units a term` : "At the roadmap’s pace",
                )
              }
            >
              <option value="">Recommended</option>
              {[12, 15, 18].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <label>
            Graduate by{" "}
            <select
              disabled={!!work.busy}
              value={options.graduate_by ?? ""}
              onChange={(e) =>
                work.whatIf(
                  { graduate_by: e.target.value || undefined },
                  e.target.value ? `Aiming for ${termLabel(e.target.value)}` : "At the recommended pace",
                )
              }
            >
              <option value="">Recommended</option>
              {nearbyTerms(0, 12).map((t) => (
                <option value={t} key={t}>
                  {termLabel(t)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {work.busy && (
          <span className="what-if-result" role="status">
            {work.busy}
          </span>
        )}
        {work.failed && <ErrorCard text={work.failed} />}
      </section>
      <div className="timeline-heading">
        <div>
          <h2>Your semester plan</h2>
          <p>The next two terms are open. Expand a later term when you need the details.</p>
        </div>
      </div>
      <nav className="year-jump" aria-label="Jump to academic year">
        <span>Jump to year</span>
        {years.map((year) => (
          <a href={`#year-${year.replace("–", "-")}`} key={year}>
            {year}
          </a>
        ))}
      </nav>
      <div className="year-plan">
        {years.map((year) => (
          <section className="academic-year" id={`year-${year.replace("–", "-")}`} key={year}>
            <div className="year-heading">
              <span>{year}</span>
              <i />
            </div>
            {semesters
              .filter((s) => yearOf(s.term) === year)
              .map((s) => {
                const ti = semesters.indexOf(s);
                const isLast = ti === semesters.length - 1;
                const codes = s.courses.filter((c): c is string => !isSlot(c));
                const count = s.courses.length;
                return (
                  <details
                    className={`term-card vertical ${isLast ? "graduation-term" : ""}`}
                    open={ti < 2}
                    key={s.term}
                  >
                    <summary className="term-head">
                      <div>
                        <span>
                          {ti === 0 ? "Next term" : isLast ? "Final term" : `Term ${ti + 1}`}
                        </span>
                        <h3>{termLabel(s.term)}</h3>
                      </div>
                      <p>
                        {unitText(termUnits(s, info))} <i>·</i> {count} {count === 1 ? "course" : "courses"}
                        {ti >= 2 && (
                          <small>
                            {" "}
                            · {codes.slice(0, 2).join(", ")}
                            {count > 2 ? ` + ${count - Math.min(codes.length, 2)} more` : ""}
                          </small>
                        )}
                      </p>
                      {isLast && (
                        <strong className="graduation-marker">
                          <Icon name="check" /> Graduation
                        </strong>
                      )}
                      <Icon name="chevron" />
                    </summary>
                    <div className="term-courses single-column">
                      {codes.map((code) => (
                        <button className="course-row" onClick={() => openCourse(code)} key={code}>
                          <span>
                            <b>{code}</b>
                            <small>{info[code]?.title}</small>
                            {countsFor(code, work.picks, audit) && (
                              <em>Counts for {countsFor(code, work.picks, audit)}</em>
                            )}
                            {work.picks.some((p) => p.code === code && !p.readiness) && (
                              <em className="ai-pick">AI pick</em>
                            )}
                          </span>
                          <i>{unitText(info[code]?.units)}</i>
                          <Icon name="chevron" size={15} />
                        </button>
                      ))}
                      {s.courses.filter(isSlot).map((slot, si) => (
                        <button
                          id={slots[0]?.slot === slot ? "first-open-slot" : undefined}
                          className="slot-card list-slot"
                          onClick={() => openChoice(slot, s.term)}
                          key={`${slot.slot}-${si}`}
                        >
                          <span>
                            <Icon name="plus" />
                          </span>
                          <div>
                            <b>{slotLabel(slot, audit)}</b>
                            <small>
                              {slot.units
                                ? `Open choice · ${unitText(slot.units)}`
                                : "A course you pick for another requirement can cover this"}
                            </small>
                          </div>
                          <strong>
                            Choose <Icon name="arrow" size={14} />
                          </strong>
                        </button>
                      ))}
                    </div>
                    {ti === 0 && (
                      <Button kind="secondary" className="term-schedule" onClick={openSchedule}>
                        View class schedule <Icon name="calendar" />
                      </Button>
                    )}
                  </details>
                );
              })}
          </section>
        ))}
      </div>
      <div className="plan-lower">
        {!!warnings.length && (
          <details className="warning-card collapsible">
            <summary>
              <Icon name="warning" /> <b>{warnings.length} things to check</b>
              <span className="summary-chevron" aria-hidden="true">
                <Icon name="chevron" />
              </span>
            </summary>
            <ul>
              {warnings.map((w) => (
                <li key={w}>{plainText(w, audit)}</li>
              ))}
            </ul>
          </details>
        )}
        <section className="advisor-card">
          <div className="advisor-card-head">
            <Icon name="info" /> <h2>Questions? Talk to an advisor</h2>
            {!!advisors.length && <span>{advisors.length} things worth asking</span>}
          </div>
          <p className="advisor-fallback">
            GatorPath is a planning guide. For any question about your plan, talk to an advisor before you
            register.
          </p>
          <AdvisorCards items={advisors} audit={audit} />
        </section>
      </div>
      <div className="plan-actions">
        <Button kind="secondary" icon="download" onClick={() => window.print()}>
          Print my plan
        </Button>
      </div>
    </div>
  );
}

/** Done, in progress and left in one group, whichever way the rules count it. */
function groupProgress(g: Group) {
  const courses = g.counted.length + g.in_progress.length + (g.remaining?.length ?? 0);
  const done = isDone(g);
  if (courses && g.remaining) {
    return {
      percent: done ? 100 : (g.counted.length / courses) * 100,
      label: `${g.counted.length} / ${courses} done`,
    };
  }
  const needed = g.units_needed ?? 0;
  const have = g.units_done ?? 0;
  return {
    percent: done ? 100 : needed ? (have / needed) * 100 : 0,
    label: needed ? `${have} / ${needed} units` : done ? "Done" : "Not yet",
  };
}

function ProgressView({ work }: { work: Work }) {
  return (
    <div className="app-content">
      <div className="page-title">
        <h1>Your degree progress</h1>
        <p>See what’s done, planned, and still remaining.</p>
      </div>
      <DegreeProgress audit={work.audit} semesters={work.semesters} />
    </div>
  );
}

/** Units and every requirement, done to left. With a plan it says what's planned; without one (Review, straight from
 * the DPR) it reads like the DPR: Completed, In progress, Incomplete, GE and university requirements before the major. */
function DegreeProgress({
  audit,
  semesters,
  bars = true,
  dpr,
}: {
  audit: Audit;
  semesters?: Semester[];
  bars?: boolean;
  dpr?: DprMissing;
}) {
  const plannedTerm = (code: string) => semesters?.find((s) => s.courses.includes(code))?.term;
  const plannedSlot = semesters
    ? (g: Group) => {
        const term = semesters.find((s) => s.courses.some((c) => isSlot(c) && c.slot === g.id))?.term;
        return term && `Planned · ${termLabel(term)}`;
      }
    : undefined;
  const [doneWord, leftWord] = semesters ? ["Done", "Remaining"] : ["Completed", "Incomplete"];
  const buckets: [string, Group[]][] = [
    ["General Education", audit.groups.filter((g) => g.id.startsWith("ge_"))],
    ["SF State Studies", audit.groups.filter((g) => g.id.startsWith("sfss_"))],
    ["American Institutions", audit.groups.filter((g) => g.id.startsWith("ai_"))],
    [
      "Other university requirements",
      audit.groups.filter((g) => g.kind === "university" && !/^(ge|sfss|ai)_/.test(g.id)),
    ],
  ];
  const major = audit.groups
    .filter((g) => g.kind === "major")
    .map((g) => {
      const p = groupProgress(g);
      return {
        key: g.id,
        title: g.title,
        percent: p.percent,
        label: p.label,
        body: (
          <div className="req-courses">
            {dpr?.missing.includes(g.id) && (
              <button className="let-pick" onClick={() => dpr.set([g.id], !dpr.left.includes(g.id))}>
                {dpr.left.includes(g.id) ? "Not on your DPR · Put it back" : "Not on your DPR · Leave it out"}
              </button>
            )}
            {g.counted.map((c) => (
              <CourseStatus name={c} type="done" label={doneWord} key={c} />
            ))}
            {g.in_progress.map((c) => (
              <CourseStatus name={c} type="progress" label="In progress" key={c} />
            ))}
            {g.remaining?.map((c) => (
              <CourseStatus
                name={c}
                type="remaining"
                label={plannedTerm(c) ? `Planned · ${termLabel(plannedTerm(c))}` : leftWord}
                key={c}
              />
            ))}
          </div>
        ),
      };
    });
  const university = buckets
    .filter(([, groups]) => groups.length)
    .map(([title, groups]) => {
      const met = groups.filter(isDone).length;
      return {
        key: title,
        title,
        percent: (met / groups.length) * 100,
        label: `${met} / ${groups.length} done`,
        body: <GeRequirementRows groups={groups} plannedIn={plannedSlot} dpr={dpr} />,
      };
    });
  const t = audit.totals;
  return (
    <>
      {bars && (
        <section className="progress-summary" aria-label="Units">
          <div className="progress-meters">
            <UnitBar value={t.units.value} going={t.units_in_progress} total={t.units.needed ?? 120} label="Total units" />
            <UnitBar
              value={t.upper_division_units.value}
              going={t.upper_division_units_in_progress}
              total={t.upper_division_units.needed ?? 0}
              label="Upper-division units"
            />
          </div>
          <div className="status-key">
            <span>Status key</span>
            <StatusBadge type="done">{doneWord}</StatusBadge>
            <StatusBadge type="progress">In progress</StatusBadge>
            {semesters && <StatusBadge type="planned">Planned</StatusBadge>}
            <StatusBadge type="remaining">{leftWord}</StatusBadge>
          </div>
        </section>
      )}
      <SectionCard
        title="Degree requirements"
        count={`${t.units.value + t.units_in_progress} of ${t.units.needed} units${t.units_in_progress ? `, incl. ${t.units_in_progress} in progress` : ""}`}
      >
        <div className="requirement-list">
          {(semesters ? [...major, ...university] : [...university, ...major]).map((r, i) => (
            <details key={r.key} open={i === 0}>
              <summary>
                <span className="req-check" aria-hidden="true">
                  {r.percent === 100 ? <Icon name="check" /> : null}
                </span>
                <b>{r.title}</b>
                <div className="mini-progress">
                  <i style={{ width: `${r.percent}%` }} />
                </div>
                <small>{r.label}</small>
                <Icon name="chevron" />
              </summary>
              {r.body}
            </details>
          ))}
        </div>
      </SectionCard>
    </>
  );
}
/** Done, then in progress after it in a lighter shade: the DPR counts both. */
function UnitTrack({ value, going = 0, total, label }: { value: number; going?: number; total: number; label: string }) {
  const share = (x: number) => (total ? Math.min(100, (x / total) * 100) : 0);
  return (
    <div className="unit-bar-track" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={total} aria-label={label}>
      <i style={{ width: `${share(value)}%` }} />
      {!!going && <i className="going" style={{ width: `${Math.min(share(going), 100 - share(value))}%` }} />}
    </div>
  );
}
function UnitBar({ value, going = 0, total, label }: { value: number; going?: number; total: number; label: string }) {
  return (
    <div className="unit-bar">
      <div>
        <b>{label}</b>
        <span>
          {value + going} of {total}
          {!!going && `, incl. ${going} in progress`}
        </span>
      </div>
      <UnitTrack value={value} going={going} total={total} label={label} />
    </div>
  );
}
function CourseStatus({
  name,
  type,
  label,
}: {
  name: string;
  type: "done" | "progress" | "remaining";
  label: string;
}) {
  return (
    <div>
      <span>{name}</span>
      <StatusBadge type={type}>{label}</StatusBadge>
    </div>
  );
}

type ChoiceRow = { id: string; title: string; term: string; units?: number; pick?: Pick };

function ChoiceRequirementRows({
  rows,
  audit,
  openPicker,
}: {
  rows: ChoiceRow[];
  audit: Audit;
  openPicker: (target: Target) => void;
}) {
  return (
    <div className="choice-requirements">
      {rows.map((r, i) => (
        <div className="choice-requirement-row" key={`${r.id}-${r.term}-${i}`}>
          <div>
            <span>{r.id === "elective" ? "Any course" : "Requirement"}</span>
            <b>{r.title}</b>
          </div>
          <div className="planned-choice">
            <small>In your plan</small>
            {r.pick ? <b>{r.pick.code}</b> : <b className="not-chosen">Not chosen yet</b>}
            <span>{termLabel(r.term)}</span>
            {!!r.pick?.covers.length && <em>Counts twice</em>}
          </div>
          <div className="alternative-choices">
            {r.units ? (
              <>
                <small>Units</small>
                <span>{r.units}</span>
              </>
            ) : null}
          </div>
          <button
            onClick={() =>
              openPicker({ group: r.id, term: r.term, title: r.title, replacing: r.pick?.code })
            }
          >
            {r.pick ? "Change" : "Choose a course"} <Icon name="arrow" size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}

function ElectivesView({ work, openPicker }: { work: Work; openPicker: (target: Target) => void }) {
  const { audit, check, info, picks, semesters, student } = work;
  const rows: ChoiceRow[] = [
    ...semesters.flatMap((s) =>
      s.courses.filter(isSlot).map((slot) => ({
        id: slot.slot,
        title: slotLabel(slot, audit),
        term: s.term,
        units: slot.units,
      })),
    ),
    ...picks.map((pick) => ({
      id: pick.group,
      title: pick.group === "elective" ? "Free elective: any course" : (audit.groups.find((g) => g.id === pick.group)?.title ?? pick.group),
      term: pick.term,
      pick,
    })),
  ];
  const major = rows.filter((r) => audit.groups.find((g) => g.id === r.id)?.kind === "major");
  const ge = rows.filter((r) => r.id.startsWith("ge_"));
  const free = rows.filter((r) => r.id === "elective");
  const studies = rows.filter((r) => !major.includes(r) && !ge.includes(r) && !free.includes(r));
  const count = (list: ChoiceRow[]) => `${list.filter((r) => r.pick).length} chosen, ${list.filter((r) => !r.pick).length} to go`;
  const short = audit.groups.find((g) => g.min_units_from && !isDone(g));
  const inSubject = short?.min_units_from
    ? picks
        .filter((p) => p.group === short.id && p.code.startsWith(short.min_units_from!.subject))
        .reduce((total, p) => total + unitsOf(p.code, info), short.min_units_from.done)
    : 0;
  return (
    <div className="app-content">
      <div className="page-title">
        <h1>Electives & GE</h1>
        <p>
          These are the requirements where you get to choose. Change a class here to see its options, or ask
          the chat.
          {student.goal && student.goal !== "Undecided" ? ` Your focus: ${student.goal}.` : ""}
        </p>
      </div>
      {!check.valid && <ProblemPanel errors={check.errors} audit={audit} ask={work.ask} />}
      {work.busy && <Loading label={work.busy} />}
      {work.failed && <ErrorCard text={work.failed} />}
      {!!major.length && (
        <SectionCard title="Major electives" count={count(major)}>
          {short?.min_units_from && (
            <div className="major-electives-summary">
              <div className="csc-unit-progress">
                <div>
                  <b>
                    {inSubject} of {short.min_units_from.units} required {short.min_units_from.subject} units
                  </b>
                  <span>{Math.min(100, Math.round((inSubject / short.min_units_from.units) * 100))}%</span>
                </div>
                <div>
                  <i style={{ width: `${Math.min(100, (inSubject / short.min_units_from.units) * 100)}%` }} />
                </div>
              </div>
            </div>
          )}
          <ChoiceRequirementRows rows={major} audit={audit} openPicker={openPicker} />
        </SectionCard>
      )}
      {!!ge.length && (
        <SectionCard title="GE still needed" count={count(ge)}>
          <ChoiceRequirementRows rows={ge} audit={audit} openPicker={openPicker} />
        </SectionCard>
      )}
      {!!studies.length && (
        <SectionCard title="SF State Studies & American Institutions" count={count(studies)}>
          <ChoiceRequirementRows rows={studies} audit={audit} openPicker={openPicker} />
        </SectionCard>
      )}
      {!!free.length && (
        <SectionCard title="Free electives" count={count(free)}>
          <ChoiceRequirementRows rows={free} audit={audit} openPicker={openPicker} />
        </SectionCard>
      )}
      {!rows.length && <p className="still-to-do">Nothing left to choose in this plan.</p>}
    </div>
  );
}

const CALENDAR_DAYS = [
  ["MONDAY", "Mo"],
  ["TUESDAY", "Tu"],
  ["WEDNESDAY", "We"],
  ["THURSDAY", "Th"],
  ["FRIDAY", "Fr"],
];
const CLASS_SEARCH = "https://webapps.sfsu.edu/public/classservices/classsearch";
function hourOf(text?: string) {
  const m = text?.match(/(\d+):(\d+)\s*(AM|PM)/);
  return m ? (Number(m[1]) % 12) + (m[3] === "PM" ? 12 : 0) + Number(m[2]) / 60 : null;
}
function hours(meeting: Meeting) {
  const [from, to] = (meeting.time ?? "").split(" - ");
  const start = hourOf(from);
  const end = hourOf(to);
  return start === null || end === null ? null : { start, end };
}
/** A section's meetings, each once: Class Search lists a co-taught meeting once per instructor. */
const when = (s: Section) =>
  [...new Set(s.meetings.map((m) => [m.days, m.time, m.where].filter(Boolean).join(" ")))].join("; ") || s.mode;
/** Who teaches it, each name once, linked to Rate My Professors (student opinions) where there's a search. */
function Instructors({ section }: { section: Section }) {
  const names = [...new Set((section.instructor ?? "").split(", ").filter(Boolean))];
  if (!names.length || names.every((n) => n === "To be announced")) return <> · Instructor to be announced</>;
  const links = section.rate_my_professors ?? {};
  return (
    <>
      {" · "}
      {names.map((name, i) => (
        <span key={name}>
          {i > 0 && ", "}
          {links[name] ? (
            <a href={links[name]} target="_blank" rel="noreferrer" title="Rate My Professors: student opinions">
              {name}
            </a>
          ) : (
            name
          )}
        </span>
      ))}
      {names.some((n) => links[n]) && <span className="rmp-note"> (names link to Rate My Professors)</span>}
    </>
  );
}
const seats = (s: Section) =>
  s.seats_open ? `${s.seats_open} seats open` : s.waitlist_open ? "Full · waitlist open" : "Full";

function ScheduleView({
  work,
  openPlan,
  toast,
}: {
  work: Work;
  openPlan: () => void;
  toast: (x: string) => void;
}) {
  const first = work.semesters[0];
  const codes = first.courses.filter((c): c is string => !isSlot(c));
  const label = termLabel(first.term);
  const online = work.picks.filter((p) => p.online && p.term === first.term).map((p) => p.code);
  const keep = work.sections[first.term] ?? [];
  const result = useLoad(
    () => getSections(first.term, codes, online, keep),
    [first.term, codes.join(), online.join(), keep.join()],
  );
  const [preview, setPreview] = useState<"" | "ready" | "not-offered" | "unpublished" | "no-fit" | "full">("");
  const [peek, setPeek] = useState<{ code: string; nbr: string } | null>(null); // another section, on the calendar
  const [trying, setTrying] = useState(false);
  if (!codes.length) return <div className="app-content"><p>Choose this term’s courses first.</p></div>;
  if (result.error) return <div className="app-content"><ErrorCard text={result.error} retry={result.retry} /></div>;
  if (!result.data) return <div className="app-content"><Loading label={`Finding ${label} sections…`} /></div>;
  const r = result.data;
  const classes = Object.entries(r.schedule ?? {}).map(([code, numbers]) => ({
    code,
    picked: r.sections[code].filter((s) => numbers.includes(s.class_nbr)),
    others: r.sections[code].filter((s) => !numbers.includes(s.class_nbr)),
  }));
  const derived =
    r.schedule === null && r.always_clash.length
      ? "no-fit"
      : !Object.keys(r.sections).length // no sections at all: an unpublished term, not a gap in one course
        ? r.unknown.length
          ? "unpublished"
          : "not-offered"
        : "ready";
  const scheduleState = preview || derived;
  const problemContent = {
    "not-offered": [`${r.not_offered[0] ?? "A course"} isn’t offered in ${label}`, "Move it in your plan", "button"],
    unpublished: [`${label} schedule isn’t published yet`, "Check Class Search", "link"],
    "no-fit": [
      `No combination fits: ${r.always_clash[0]?.join(" and ") ?? "two courses"} always overlap`,
      "Move one to another term",
      "button",
    ],
    full: ["All sections full", "Join a waitlist or pick another section", "button"],
  } as const;
  // The section being looked at, as this answer has it (its clashes are against this schedule)
  const shown = peek ? r.sections[peek.code]?.find((s) => s.class_nbr === peek.nbr) : undefined;
  const clashing = (shown?.clashes_with ?? []).map((x) => x.slice(0, x.lastIndexOf(" "))); // "MATH 226 01" -> course
  const timed = (c: (typeof classes)[number], i: number, s: Section, look = "") =>
    s.meetings.flatMap((m) => {
      const time = hours(m);
      return time && m.days ? m.days.split(" ").map((day) => ({ c, i, s, m, time, day, look })) : [];
    });
  const blocks = [
    ...classes.flatMap((c, i) =>
      c.picked.flatMap((s) =>
        timed(c, i, s, c.code === peek?.code ? "faded" : clashing.includes(c.code) ? "clash" : ""),
      ),
    ),
    ...(shown && peek
      ? timed(
          classes.find((c) => c.code === peek.code)!,
          classes.findIndex((c) => c.code === peek.code),
          shown,
          clashing.length ? "preview clash" : "preview",
        )
      : []),
  ];
  const use = async () => {
    if (!shown || !peek) return;
    const theirs = r.sections[peek.code].map((s) => s.class_nbr); // one choice per class
    const next = [...keep.filter((n) => !theirs.includes(n)), shown.class_nbr];
    setTrying(true);
    try {
      const tried = await getSections(first.term, codes, online, next);
      if (!tried.schedule) {
        const other = tried.always_clash.flat().filter((c) => c !== peek.code);
        return toast(`${peek.code} ${shown.section} can’t fit: it overlaps every section of ${other.join(", ")}`);
      }
      setPeek(null);
      work.setSections(first.term, next);
      toast(`${peek.code} section ${shown.section} is in your schedule`);
    } catch (e) {
      toast(message(e));
    } finally {
      setTrying(false);
    }
  };
  return (
    <div className="app-content">
      <div className="schedule-title">
        <div>
          <h1>Your {label} schedule</h1>
          <p>One clash-free combination based on your plan.</p>
        </div>
      </div>
      {DEMO && (
        <div className="variant-switcher schedule-variants">
          <span>Preview schedule state</span>
          {[
            ["ready", "Published"],
            ["not-offered", "Not offered"],
            ["unpublished", "Not published"],
            ["no-fit", "No fit"],
            ["full", "Sections full"],
          ].map(([value, text]) => (
            <button
              className={scheduleState === value ? "active" : ""}
              onClick={() => setPreview(value as typeof preview)}
              key={value}
            >
              {text}
            </button>
          ))}
        </div>
      )}
      {scheduleState !== "ready" ? (
        <div className={`schedule-problem-frame ${scheduleState}`}>
          <span>
            <Icon
              name={
                scheduleState === "unpublished"
                  ? "clock"
                  : scheduleState === "no-fit"
                    ? "x"
                    : "warning"
              }
            />
          </span>
          <div>
            <h2>{problemContent[scheduleState][0]}</h2>
            <p>
              {scheduleState === "no-fit"
                ? "Move one course so we can build a clash-free schedule."
                : scheduleState === "full"
                  ? "No open seats remain in this course right now."
                  : scheduleState === "unpublished"
                    ? "SF State hasn’t posted this term’s classes yet, so there are no sections to show. Your plan is fine."
                    : "Your degree plan is safe; this only affects next term’s schedule."}
            </p>
            {problemContent[scheduleState][2] === "link" ? (
              <a href={CLASS_SEARCH} target="_blank" rel="noreferrer">
                {problemContent[scheduleState][1]} <Icon name="arrow" size={13} />
              </a>
            ) : (
              <Button kind="secondary" onClick={openPlan}>
                {problemContent[scheduleState][1]}
              </Button>
            )}
          </div>
        </div>
      ) : (
        <>
          {[...r.not_offered, ...r.unknown].map((code) => (
            <p className="online-note" key={code}>
              <Icon name="warning" size={15} /> <b>{code}</b>{" "}
              {r.not_offered.includes(code)
                ? `has no section in ${label}. Move it in your plan.`
                : "isn’t in our schedule data. Check Class Search."}
            </p>
          ))}
          <div className="schedule-controls">
            <div>
              <b>
                No time clashes{r.sets > 1 ? `: one of ${r.sets} ways to fit these classes` : ""}
              </b>
            </div>
          </div>
          {shown && peek && (
            <div className={`peek-bar${clashing.length ? " clash" : ""}`} role="status">
              <p>
                <b>
                  {peek.code} section {shown.section}
                </b>{" "}
                · {when(shown)} ·{" "}
                {clashing.length
                  ? `Clashes with ${shown.clashes_with!.join(", ")} as your schedule is now`
                  : "Fits with your other classes"}
              </p>
              <div>
                <Button onClick={use} disabled={trying || work.aiBusy}>
                  {clashing.length ? "Try it, moving the others" : "Use this section"}
                </Button>
                <Button kind="ghost" onClick={() => setPeek(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
          <div className="calendar-card hourly">
            <div className="calendar-head">
              {["TIME", "MON", "TUE", "WED", "THU", "FRI"].map((x) => (
                <span key={x}>{x}</span>
              ))}
            </div>
            <div className="calendar-body">
              <div className="times">
                {["8 AM", "9 AM", "10 AM", "11 AM", "12 PM", "1 PM", "2 PM", "3 PM", "4 PM", "5 PM", "6 PM", "7 PM", "8 PM"].map(
                  (x) => (
                    <span key={x}>{x}</span>
                  ),
                )}
              </div>
              <div className="day-grid">
                {[0, 1, 2, 3, 4].map((x) => (
                  <i key={x} />
                ))}
                {blocks
                  .filter((b) => CALENDAR_DAYS.some(([, code]) => code === b.day))
                  .map((b) => (
                    <div
                      className={`cal-block c${b.i % 3} ${b.look}`}
                      key={`${b.look}${b.s.class_nbr}${b.m.time}${b.day}`}
                      style={{
                        top: (b.time.start - 8) * 52 + 1,
                        height: (b.time.end - b.time.start) * 52 - 3,
                        left: `calc(${CALENDAR_DAYS.findIndex(([, code]) => code === b.day)} * 20% + 4px)`,
                      }}
                    >
                      <b>
                        {b.c.code} {b.s.component !== "LEC" ? b.s.component : ""}
                      </b>
                      <span>
                        {b.m.time}
                        {b.s.mode.startsWith("Hybrid") ? " · Hybrid" : b.s.mode.startsWith("Online") ? " · Online" : ""}
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          </div>
          {classes
            .filter((c) => !c.picked.some((s) => s.meetings.some((m) => m.days)))
            .map((c) => (
              <p className="online-note" key={c.code}>
                <Icon name="info" size={15} /> <b>{c.code}</b> has no set meeting time, so it isn’t on
                the calendar.
              </p>
            ))}
          <div className="mobile-day-list">
            {CALENDAR_DAYS.map(([day, code]) => (
              <div key={day}>
                <b>{day}</b>
                <section>
                  {blocks
                    .filter((b) => b.day === code)
                    .sort((a, b) => a.time.start - b.time.start)
                    .map((b) => (
                      <span className={b.look} key={`${b.look}${b.s.class_nbr}${b.m.time}`}>
                        <i className={`class-dot c${b.i % 3}`} />
                        <strong>{b.c.code}</strong>
                        {b.m.time}
                      </span>
                    ))}
                </section>
              </div>
            ))}
          </div>
          <div className="section-list">
            {classes.map((c) => {
              const [main, ...linked] = c.picked;
              const theirs = r.sections[c.code].map((s) => s.class_nbr);
              const mine = keep.some((n) => theirs.includes(n));
              return (
                <article className="section-detail" key={c.code}>
                  <div className="section-main">
                    <span>
                      <b>{c.code}</b>
                      <StatusBadge type={main.seats_open ? "ready" : "warning"}>{seats(main)}</StatusBadge>
                      {mine && (
                        <>
                          <em className="your-pick">Your choice</em>
                          <button
                            className="let-pick"
                            disabled={work.aiBusy}
                            onClick={() => work.setSections(first.term, keep.filter((n) => !theirs.includes(n)))}
                          >
                            Let GatorPath pick
                          </button>
                        </>
                      )}
                    </span>
                    <p>
                      Section {main.section} · {when(main)}
                    </p>
                    {linked.map((s) => (
                      <p className="linked-lab" key={s.class_nbr}>
                        <Icon name="route" size={13} /> Includes {s.component} {s.section} · {when(s)} · Class #
                        {s.class_nbr}
                      </p>
                    ))}
                    <small>
                      {main.mode}
                      <Instructors section={main} />
                    </small>
                    {!!c.others.length && (
                      <details className="other-sections">
                        <summary>
                          Other sections <Icon name="chevron" />
                        </summary>
                        {c.others.map((o) => (
                          <button
                            type="button"
                            className={o.clashes_with?.length ? "clashes" : ""}
                            aria-pressed={peek?.nbr === o.class_nbr}
                            onClick={() => {
                              setPeek({ code: c.code, nbr: o.class_nbr });
                              document.querySelector(".schedule-controls")?.scrollIntoView({ behavior: "smooth", block: "start" });
                            }}
                            key={o.class_nbr}
                          >
                            <span>
                              Section {o.section} · {when(o)} · #{o.class_nbr}
                            </span>
                            {o.clashes_with && (
                              <small>
                                {o.clashes_with.length
                                  ? `Clashes with ${o.clashes_with.join(", ")}`
                                  : "Fits instead"}
                              </small>
                            )}
                          </button>
                        ))}
                      </details>
                    )}
                  </div>
                  <div className="class-num">
                    <small>Class number</small>
                    <b>#{main.class_nbr}</b>
                    <button
                      onClick={() => {
                        navigator.clipboard?.writeText(main.class_nbr).catch(() => {});
                        toast(`${main.class_nbr} copied.`);
                      }}
                    >
                      <Icon name="copy" /> Copy
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
          {r.scraped_at && (
            <div className="schedule-note">
              <Icon name="clock" />
              <span>
                Seats and rooms as of {new Date(r.scraped_at).toLocaleDateString()}. Confirm in{" "}
                <a href={CLASS_SEARCH} target="_blank" rel="noreferrer">
                  Class Search
                </a>{" "}
                before registering.
              </span>
            </div>
          )}
          {r.warnings
            .filter((w) => !w.startsWith("Class Search as of"))
            .map((w) => (
              <div className="schedule-note" key={w}>
                <Icon name="warning" /> <span>{plainText(w, work.audit)}</span>
              </div>
            ))}
        </>
      )}
    </div>
  );
}

function useDialog(close: () => void) {
  const ref = useRef<HTMLElement>(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
      if (e.key === "Tab" && ref.current) {
        const items = ref.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], select, input, summary, [tabindex]:not([tabindex="-1"])',
        );
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, []);
  return ref;
}

function offeredText(o?: Offered | null) {
  if (!o) return "No offering history here: check Class Search";
  const ran = (["fall", "spring", "summer"] as const)
    .filter((season) => o[season])
    .map((season) => `${season} ${o[season]![0]} of ${o[season]![1]}`);
  return `Ran: ${ran.join(", ")}${o.last ? ` · last ran ${termLabel(o.last)}` : ""}`;
}

function OptionCard({
  option: o,
  chosen,
  audit,
  choose,
}: {
  option: Option;
  chosen: boolean;
  audit: Audit;
  choose: () => void;
}) {
  const blocked = o.readiness === "blocked";
  const covers = o.also_covers.map((id) => audit.groups.find((g) => g.id === id)?.title ?? id);
  return (
    <article className={`elective-card ${chosen ? "chosen" : ""}`}>
      <div className="elective-card-top">
        <div>
          <b>
            {o.code} · {o.title}
          </b>
          <small>
            {unitText(o.units)} · Bulletin p.{o.source_page}
          </small>
        </div>
        <StatusBadge type={o.readiness === "ready" ? "ready" : "warning"}>
          {o.readiness === "ready" ? "Ready" : blocked ? "Not yet" : "Check"}
        </StatusBadge>
      </div>
      {o.description && <p>{o.description}</p>}
      {[...(o.cannot_check ?? []), ...(o.blocked_by ?? [])].map((reason) => (
        <p className="check-reason" key={reason}>
          <Icon name="warning" size={13} />
          {plainText(reason)}
        </p>
      ))}
      {o.ready_by && (
        <p className="check-reason">
          <Icon name="clock" size={13} />
          Opens up in {termLabel(o.ready_by)}
        </p>
      )}
      {o.note && <p className="check-reason">{plainText(o.note)}</p>}
      <p>{offeredText(o.offered)}</p>
      {o.not_offered && (
        <p className="rare-note">
          <Icon name="warning" size={13} /> {plainText(o.not_offered)}
        </p>
      )}
      {o.readiness === "ready" && (
        <p className="ready-reason">
          <Icon name="check" size={13} /> Prerequisites met by this term
        </p>
      )}
      {!!covers.length && <span className="counts-twice">Counts twice · Also covers: {covers.join(", ")}</span>}
      <div className="elective-actions">
        <Button kind={chosen ? "secondary" : "primary"} disabled={blocked || chosen} onClick={choose}>
          {chosen ? (
            <>
              <Icon name="check" /> Chosen
            </>
          ) : (
            "Choose"
          )}
        </Button>
      </div>
    </article>
  );
}

function ElectiveDrawer({
  work,
  target,
  close,
  choose,
}: {
  work: Work;
  target: Target;
  close: () => void;
  choose: (code: string, option?: Option) => void;
}) {
  const dialogRef = useDialog(close);
  const result = useLoad(
    () => getElectives(work.student, target.group, { semesters: work.semesters }, target.term),
    [target],
  );
  const options = result.data?.options ?? [];
  const open = options.filter((o) => o.readiness !== "blocked");
  const blocked = options.filter((o) => o.readiness === "blocked");
  const min = result.data?.min_units_from;
  const card = (o: Option) => (
    <OptionCard
      option={o}
      chosen={o.code === target.replacing}
      audit={work.audit}
      choose={() => choose(o.code, o)}
      key={o.code}
    />
  );
  return (
    <div className="overlay" onMouseDown={close}>
      <aside
        className="drawer elective-drawer"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Choose courses"
        tabIndex={-1}
        ref={dialogRef}
      >
        <div className="drawer-head">
          <div>
            <h2>{target.title}</h2>
            <p>
              For {termLabel(target.term)}.
              {min ? ` At least ${min.units} units must be in ${min.subject}.` : ""}
              {work.student.goal && work.student.goal !== "Undecided" ? ` Your focus: ${work.student.goal}.` : ""}
            </p>
          </div>
          <button onClick={close} aria-label="Close">
            <Icon name="x" />
          </button>
        </div>
        {result.loading && <Loading label="Finding courses that fit…" />}
        {result.error && <ErrorCard text={result.error} retry={result.retry} />}
        {result.data?.approval && (
          <p className="check-reason">
            <Icon name="warning" size={13} />
            {result.data.approval}. {ASK_ADVISOR} which courses count.
          </p>
        )}
        {!!options.length && (
          <>
            <div className="sort-row">
              <span>
                Sorted by <b>readiness, then what else each course covers</b>
              </span>
            </div>
            <div className="elective-list">{open.map(card)}</div>
            {!!blocked.length && (
              <details className="other-sections">
                <summary>
                  {blocked.length} more that aren’t ready by {termLabel(target.term)}{" "}
                  <Icon name="chevron" />
                </summary>
                <div className="elective-list">{blocked.map(card)}</div>
              </details>
            )}
          </>
        )}
        <div className="drawer-footer">
          <Button kind="secondary" onClick={close}>
            Close
          </Button>
        </div>
      </aside>
    </div>
  );
}

function CourseDrawer({ code, why, close }: { code: string; why?: string; close: () => void }) {
  const dialogRef = useDialog(close);
  const course = useLoad(() => getCourse(code), [code]);
  const c = course.data;
  const seasons = (["fall", "spring", "summer"] as const).filter((s) => c?.offered_terms?.[s]?.[0]);
  return (
    <div className="overlay" onMouseDown={close}>
      <aside
        className="drawer course-drawer"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Course details"
        tabIndex={-1}
        ref={dialogRef}
      >
        <div className="drawer-head">
          <div>
            <h2>{code}</h2>
            {c && (
              <p>
                {c.title} ·{" "}
                {c.units_min === c.units_max ? c.units_min : `${c.units_min}-${c.units_max}`} units
              </p>
            )}
          </div>
          <button onClick={close} aria-label="Close">
            <Icon name="x" />
          </button>
        </div>
        {course.error && <ErrorCard text={course.error} retry={course.retry} />}
        {course.loading && <Loading label="Finding it in the Bulletin…" />}
        {c && (
          <>
            <span className="bulletin-ref">
              <Icon name="book" size={14} /> Bulletin p.{c.source_page}
            </span>
            {c.description && (
              <div className="detail-block">
                <h3>Description</h3>
                <p>{c.description}</p>
              </div>
            )}
            <div className="detail-block">
              <h3>
                Prerequisites <Tooltip text="A prerequisite is a course you need to finish first." />
              </h3>
              <p>{c.prereq?.raw_text || "None listed in the Bulletin."}</p>
            </div>
            {why && (
              <div className="detail-block why">
                <span>
                  <Icon name="route" />
                </span>
                <div>
                  <h3>Why it’s in this term</h3>
                  <p>{why}</p>
                </div>
              </div>
            )}
            <div className="detail-block">
              <h3>Usually offered</h3>
              {seasons.length ? (
                <div className="chips">
                  {seasons.map((s) => (
                    <span key={s}>{s[0].toUpperCase() + s.slice(1)}</span>
                  ))}
                </div>
              ) : (
                <p>No offering history here: check Class Search.</p>
              )}
            </div>
          </>
        )}
        <Button onClick={close}>Got it</Button>
      </aside>
    </div>
  );
}

/** A chat reply's light markdown as React elements (nothing is injected as HTML): paragraphs, "- " and "1. " lists,
 * **bold** and links. */
function Rich({ text }: { text: string }) {
  const inline = (raw: string) =>
    plainText(raw).split(/(\*\*[^*]+\*\*|https?:\/\/[^\s)]*[^\s).,;:])/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
        <b key={i}>{part.slice(2, -2)}</b>
      ) : /^https?:\/\//.test(part) ? (
        <a key={i} href={part} target="_blank" rel="noreferrer">
          {part}
        </a>
      ) : (
        part
      ),
    );
  const blocks: { list?: "ul" | "ol"; lines: string[] }[] = [];
  for (const raw of text.split("\n")) {
    const item = raw.match(/^\s*(?:([-*•])|\d+[.)])\s+(.*)$/);
    const list = item ? (item[1] ? "ul" : "ol") : undefined;
    const last = blocks[blocks.length - 1];
    if (!raw.trim()) blocks.push({ lines: [] });
    else if (list && last?.list === list) last.lines.push(item![2]);
    else blocks.push({ list, lines: [item ? item[2] : raw.replace(/^#+\s*/, "")] });
  }
  return (
    <>
      {blocks
        .filter((b) => b.lines.length)
        .map((b, i) => {
          if (!b.list) return <p key={i}>{inline(b.lines.join(" "))}</p>;
          const List = b.list;
          return (
            <List key={i}>
              {b.lines.map((line, j) => (
                <li key={j}>{inline(line)}</li>
              ))}
            </List>
          );
        })}
    </>
  );
}

function ChatPanel({
  open,
  thread,
  sending,
  failed,
  send,
  undo,
  close,
  doing,
}: {
  open: boolean;
  thread: ChatMessage[];
  sending: boolean;
  failed: string;
  send: (text: string) => void;
  undo?: () => void;
  close: () => void;
  doing?: string; // what the AI is doing, when the page started it (filling the plan)
}) {
  const [text, setText] = useState("");
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!sending) return setSeconds(0);
    const started = Date.now();
    const tick = setInterval(() => setSeconds(Math.round((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(tick);
  }, [sending]);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); // returns a Promise now: an effect's return must not be it
  }, [thread, sending, failed]);
  const submit = (ask: string) => {
    if (!ask.trim() || sending) return;
    setText("");
    send(ask.trim());
  };
  return (
    <aside className={`chat-dock ${open ? "open" : ""}`} aria-label="Chat with GatorPath">
      <div className="chat-dock-head">
        <div>
          <h2>Ask GatorPath</h2>
          <p>Ask anything, or tell it what to change. Your plan updates beside you.</p>
        </div>
        <button className="chat-close" onClick={close} aria-label="Hide the chat">
          <Icon name="x" />
        </button>
      </div>
      <div className="chat-thread" aria-live="polite">
        {thread.map((m, i) => (
          <div className={`chat-bubble ${m.role === "user" ? "user" : "bot"}`} key={i}>
            {m.role === "user" ? m.content : <Rich text={m.content} />}
          </div>
        ))}
        {sending && (
          <div className="chat-bubble bot working" role="status">
            {doing || "Working on it…"}
            {seconds >= 3 && <small> {seconds}s</small>}
            {seconds >= 15 && <small className="working-hint">Filling a plan takes about a minute; you can keep reading it meanwhile.</small>}
          </div>
        )}
        {failed && <ErrorCard text={failed} />}
        {thread.length < 2 && !sending && (
          <div className="chat-suggestions">
            {[
              "What do I still need to graduate?",
              "Swap one of my electives for something closer to my goal",
              "Add a class in a later term",
              "One of my grades is wrong",
            ].map((ask) => (
              <button className="suggested" onClick={() => submit(ask)} key={ask}>
                {ask} <Icon name="arrow" />
              </button>
            ))}
          </div>
        )}
        <div ref={end} />
      </div>
      {undo && !sending && (
        <button className="chat-undo" onClick={undo}>
          Undo the last change
        </button>
      )}
      <p className="chat-privacy">
        <Icon name="lock" size={13} /> Claude Haiku sees your major, goal and courses, never your name, ID,
        grades or GPA. It can be wrong: for decisions,{" "}
        <a href={NAVIGATOR} target="_blank" rel="noreferrer">
          ask an advisor in Navigator
        </a>
        .
      </p>
      <div className="chat-input">
        <input
          value={text}
          maxLength={2000}
          disabled={sending}
          aria-label="Your message"
          placeholder="Ask anything, or say what to change"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit(text)}
        />
        <button aria-label="Send" disabled={sending} onClick={() => submit(text)}>
          <Icon name="arrow" />
        </button>
      </div>
    </aside>
  );
}

function StyleGuide({ close }: { close: () => void }) {
  const dialogRef = useDialog(close);
  return (
    <div className="overlay" onMouseDown={close}>
      <aside
        className="drawer style-drawer"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Style guide"
        tabIndex={-1}
        ref={dialogRef}
      >
        <div className="drawer-head">
          <div>
            <h2>GatorPath style guide</h2>
            <p>Calm, clear, and trustworthy.</p>
          </div>
          <button onClick={close} aria-label="Close">
            <Icon name="x" />
          </button>
        </div>
        <h3>Colors</h3>
        <div className="swatches">
          {[
            ["#235347", "Path green"],
            ["#F5F3EE", "Warm canvas"],
            ["#287565", "Done"],
            ["#3268B2", "In progress"],
            ["#B66A24", "Warning"],
            ["#B5413B", "Error"],
          ].map((x) => (
            <div key={x[0]}>
              <i style={{ background: x[0] }} />
              <b>{x[1]}</b>
              <small>{x[0]}</small>
            </div>
          ))}
        </div>
        <h3>Type scale</h3>
        <div className="type-scale">
          <span>Display · 52 / 56</span>
          <h2>Plan with confidence.</h2>
          <span>Heading · 28 / 34</span>
          <h3>A clear path forward</h3>
          <span>Body · 15 / 24</span>
          <p>Plain language helps students make decisions under pressure.</p>
        </div>
        <h3>Spacing & components</h3>
        <p>8px base grid · 12px controls · 18–24px cards · 32–80px sections</p>
        <div className="guide-components">
          <StatusBadge type="done">Done</StatusBadge>
          <StatusBadge type="progress">In progress</StatusBadge>
          <StatusBadge type="warning">Warning</StatusBadge>
        </div>
      </aside>
    </div>
  );
}

function AppWorkspace({ profile, built, notes }: { profile: Profile; built: Built; notes: string[] }) {
  const [tab, setTab] = useState<Tab>("plan");
  const [picker, setPicker] = useState<Target | null>(null);
  const [course, setCourse] = useState("");
  const [chat, setChat] = useState(false);
  const [docked, setDocked] = useState(true); // on a wide screen the chat sits beside the plan until hidden
  const [thread, setThread] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [chatFailed, setChatFailed] = useState("");
  const [aiDown, setAiDown] = useState(false);
  const [toast, setToast] = useState("");
  const [state, setState] = useState({
    options: built.options as Partial<Profile>,
    plan: built.plan,
    semesters: built.plan.semesters,
    check: built.plan.check ?? ({ valid: true, errors: [] } as Checked),
    info: built.plan.courses ?? {},
    picks: [] as Pick[],
    sections: {} as Record<string, string[]>,
  });
  const [busy, setBusy] = useState("");
  const [failed, setFailed] = useState("");
  const [previous, setPrevious] = useState<typeof state | null>(null);
  const student = { ...profile, ...state.options };
  const say = (content: string) => setThread((t) => [...t, { role: "assistant", content }]);
  const showToast = (x: string) => {
    setToast(x);
    setTimeout(() => setToast(""), 2500);
  };
  const attempt = async (label: string, run: () => Promise<typeof state>, done: (next: typeof state) => string) => {
    setBusy(label);
    setFailed("");
    try {
      const next = await run();
      setPrevious(state);
      setState(next);
      say(done(next));
    } catch (e) {
      setFailed(message(e));
    } finally {
      setBusy("");
    }
  };
  const whatIf = (change: Options, label: string) =>
    attempt(
      "Rebuilding your plan…",
      async () => {
        const options = { ...state.options, ...change };
        const plan = await buildPlan({ ...profile, ...options }, {}); // the chat may have changed the record too
        if (plan.needs_input) throw new Error("That change needs more about you: go back to your goals.");
        return {
          options,
          plan,
          semesters: plan.semesters,
          check: plan.check ?? { valid: true, errors: [] },
          info: plan.courses ?? {},
          picks: [],
          sections: state.sections, // a section only stays while its class does
        };
      },
      (next) =>
        `${label}: graduate ${termLabel(next.plan.est_graduation_term)}${state.picks.length ? ". Your course choices were cleared" : ""}`,
    );
  const applyFold = () => {
    const fold = state.plan.pace?.fold_last_term;
    if (!fold) return;
    const last = state.semesters[state.semesters.length - 1];
    const semesters = state.semesters
      .slice(0, -1)
      .map((s) =>
        s.term === fold.term
          ? { ...s, courses: [...s.courses, ...last.courses], max_units: fold.units }
          : s,
      );
    attempt(
      "Checking the faster plan…",
      async () => {
        const check = await checkPlan(student, { semesters });
        const picks = state.picks.map((p) => (p.term === last.term ? { ...p, term: fold.term } : p));
        return { ...state, semesters, check, picks, info: { ...state.info, ...check.courses } };
      },
      () => `Faster: graduate ${termLabel(fold.est_graduation_term)}`,
    );
  };
  const choose = (target: Target, code: string, option?: Option) => {
    setPicker(null);
    attempt(
      "Checking your plan…",
      async () => {
        const semesters = state.semesters.map((s) => {
          if (s.term !== target.term) return s;
          let placed = false;
          const courses = s.courses.map((c) => {
            const fits = target.replacing ? c === target.replacing : isSlot(c) && c.slot === target.group;
            if (placed || !fits) return c;
            placed = true;
            return code;
          });
          return { ...s, courses };
        });
        const check = await checkPlan(student, { semesters });
        const pick = {
          group: target.group,
          term: target.term,
          code,
          readiness: option?.readiness,
          covers: option?.also_covers ?? [],
        };
        return {
          ...state,
          semesters,
          check,
          info: { ...state.info, ...check.courses },
          picks: [...state.picks.filter((p) => p.code !== target.replacing), pick],
        };
      },
      (next) => (next.check.valid ? `${code} is in your plan` : `${code} is in your plan, but the plan has a problem`),
    );
  };
  // The API returns what it was sent of each term, so keep what only build_plan has (why)
  const withAnswer = (r: Assisted) => ({
    ...state,
    semesters: r.semesters.map((s) => ({ ...state.semesters.find((o) => o.term === s.term), ...s })),
    check: r.check,
    picks: r.picks,
    plan: r.rebuilt ?? state.plan,
    options: { ...state.options, ...r.options },
    info: { ...state.info, ...r.rebuilt?.courses, ...r.check.courses },
    sections: r.sections ?? state.sections,
  });
  const fill = async () => {
    setBusy("Choosing your courses with AI…");
    setFailed("");
    try {
      const r = await assist(student, state.semesters, state.picks, [], state.sections, told.current ? [] : notes);
      told.current = true;
      if (r.changed) {
        setPrevious(state);
        setState(withAnswer(r));
      }
      say(r.reply);
    } catch (e) {
      say(message(e)); // the plan works without AI: say so, without an error
      setAiDown(true);
    } finally {
      setBusy("");
    }
  };
  const send = async (text: string) => {
    const asked: ChatMessage[] = [...thread, { role: "user", content: text }];
    setThread(asked);
    setSending(true);
    setChatFailed("");
    try {
      const r = await assist(student, state.semesters, state.picks, asked, state.sections);
      setThread([...asked, { role: "assistant", content: r.reply }]);
      if (r.changed) {
        setPrevious(state);
        setState(withAnswer(r));
      }
    } catch (e) {
      setChatFailed(message(e));
    } finally {
      setSending(false);
    }
  };
  const started = useRef(false);
  const told = useRef(false); // the DPR notes go with the first request only
  useEffect(() => {
    // the first reply fills the open slots and says what the DPR import found, so it runs for either
    if (started.current || !(notes.length || state.semesters.some((s) => s.courses.some(isSlot)))) return;
    started.current = true;
    fill();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const open = () => {
      setChat(true);
      setDocked(true);
    };
    document.addEventListener("gator-ask", open);
    return () => document.removeEventListener("gator-ask", open);
  }, []);
  const work: Work = {
    ...state,
    student,
    audit: built.audit,
    busy,
    failed,
    whatIf,
    applyFold,
    fill,
    aiDown,
    aiBusy: sending || !!busy,
    ask: (text) => {
      if (sending || busy) return;
      setChat(true);
      setDocked(true);
      send(text);
    },
    setSections: (term, keep) => {
      setPrevious(state);
      setState({ ...state, sections: { ...state.sections, [term]: keep } });
    },
  };
  const undo = previous
    ? () => {
        setState(previous);
        setPrevious(null);
        say("I put your plan back the way it was.");
      }
    : undefined;
  const why = state.semesters.find((s) => s.why?.[course])?.why?.[course];
  return (
    <div className={`workspace ${docked ? "" : "chat-hidden"}`}>
      <div className="workspace-main">
        <Tabs tab={tab} setTab={setTab} />
        {tab === "plan" && (
          <PlanView
            work={work}
            openChoice={(slot, term) =>
              setPicker({ group: slot.slot, term, title: slotLabel(slot, built.audit) })
            }
            openCourse={setCourse}
            openSchedule={() => setTab("schedule")}
            toast={showToast}
          />
        )}
        {tab === "progress" && <ProgressView work={work} />}
        {tab === "electives" && (
          <ElectivesView work={work} openPicker={setPicker} />
        )}
        {tab === "schedule" && (
          <ScheduleView work={work} openPlan={() => setTab("plan")} toast={showToast} />
        )}
      </div>
      <ChatPanel
        open={chat}
        thread={thread}
        sending={sending || !!busy}
        failed={chatFailed}
        send={send}
        undo={undo}
        close={() => {
          setChat(false);
          setDocked(false);
        }}
        doing={busy}
      />
      {!docked && (
        <button className="chat-reopen" onClick={() => setDocked(true)}>
          <Icon name="spark" size={16} /> Chat
        </button>
      )}
      {picker && (
        <ElectiveDrawer
          work={work}
          target={picker}
          close={() => setPicker(null)}
          choose={(code, option) => choose(picker, code, option)}
        />
      )}
      {course && <CourseDrawer code={course} why={why} close={() => setCourse("")} />}
      {toast && (
        <div className="toast">
          <Icon name="check" />
          {toast}
        </div>
      )}
    </div>
  );
}

type Built = { options: Options; plan: PlanResult; audit: Audit };

export default function App() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [style, setStyle] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [imported, setImported] = useState<ImportResult | null>(null);
  const [options, setOptions] = useState<Options>({});
  const [needs, setNeeds] = useState<string>();
  const [built, setBuilt] = useState<Built | null>(null);
  const back = () =>
    setScreen(
      screen === "review"
        ? "record"
        : screen === "goals"
          ? "review"
          : screen === "record"
            ? "landing"
            : screen,
    );
  const home = () => {
    setProfile(null); // start over means forget it
    setImported(null);
    setOptions({});
    setNeeds(undefined);
    setBuilt(null);
    setScreen("landing");
    window.scrollTo(0, 0);
  };
  const go = (s: Screen) => {
    setScreen(s);
    window.scrollTo(0, 0);
  };
  return (
    <div className="site-shell">
      {screen !== "landing" && <Header
        screen={screen}
        onHome={home}
        onBack={back}
        onStyle={() => setStyle(true)}
      />}
      {screen === "landing" && <Landing start={() => go("record")} />}
      {screen === "record" && (
        <RecordScreen
          done={(record, dpr) => {
            setProfile(record);
            setImported(dpr ?? null);
            go(record.completed?.length || record.in_progress?.length ? "review" : "goals");
          }}
        />
      )}
      {screen === "review" && profile && (
        <ReviewScreen profile={profile} imported={imported} edit={setProfile} next={() => go("goals")} />
      )}
      {screen === "goals" && profile && (
        <GoalsScreen
          profile={profile}
          saved={options}
          needs={needs}
          build={(chosen) => {
            setOptions(chosen);
            go("building");
          }}
        />
      )}
      {screen === "building" && profile && (
        <BuildingScreen
          profile={profile}
          options={options}
          back={() => go("goals")}
          done={(plan, audit) => {
            setNeeds(plan.needs_input);
            if (plan.needs_input) return go("goals");
            setBuilt({ options, plan, audit });
            go("app");
          }}
        />
      )}
      {screen === "app" && profile && built && (
        <AppWorkspace
          profile={profile}
          built={built}
          notes={imported ? [...new Set([...imported.cross_check, ...imported.warnings])] : []}
        />
      )}
      {style && <StyleGuide close={() => setStyle(false)} />}
      {screen !== "landing" && <Footer />}
    </div>
  );
}
