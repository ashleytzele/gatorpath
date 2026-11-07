import { useEffect, useRef, useState } from "react";
import {
  buildPlan,
  checkPlan,
  EngineError,
  getAudit,
  getCourse,
  getElectives,
  getPrograms,
  getSections,
  importDpr,
  message,
  type Advisor,
  type Audit,
  type Checked,
  type CourseInfo,
  type Group,
  type ImportResult,
  type Meeting,
  type Offered,
  type Option,
  type Options,
  type PlanError,
  type PlanResult,
  type Profile,
  type Section,
  type Semester,
  type Slot,
  type Taken,
} from "./api";

// ?demo shows the prototype's preview bars. The data stays real: they only force a state on top of it.
const DEMO = new URLSearchParams(window.location.search).has("demo");

type Screen = "landing" | "record" | "review" | "goals" | "building" | "app";
type Tab = "plan" | "progress" | "electives" | "schedule";
type IconName =
  | "arrow"
  | "back"
  | "book"
  | "calendar"
  | "check"
  | "chevron"
  | "clock"
  | "copy"
  | "download"
  | "edit"
  | "file"
  | "info"
  | "lock"
  | "menu"
  | "plus"
  | "route"
  | "search"
  | "spark"
  | "upload"
  | "user"
  | "warning"
  | "x";

const iconPaths: Record<IconName, React.ReactNode> = {
  arrow: (
    <>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </>
  ),
  back: (
    <>
      <path d="m15 18-6-6 6-6" />
    </>
  ),
  book: (
    <>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4H6.5A2.5 2.5 0 0 0 4 6.5v13Z" />
      <path d="M8 7h8M8 11h6" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M16 3v4M8 3v4M3 10h18" />
    </>
  ),
  check: (
    <>
      <path d="m5 12 4 4L19 6" />
    </>
  ),
  chevron: (
    <>
      <path d="m9 18 6-6-6-6" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  copy: (
    <>
      <rect x="8" y="8" width="11" height="11" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </>
  ),
  download: (
    <>
      <path d="M12 3v12m0 0 5-5m-5 5-5-5M5 21h14" />
    </>
  ),
  edit: (
    <>
      <path d="m4 20 4.5-1 10-10a2 2 0 0 0-3-3l-10 10L4 20ZM14 7l3 3" />
    </>
  ),
  file: (
    <>
      <path d="M6 2h8l4 4v16H6z" />
      <path d="M14 2v5h5M9 13h6M9 17h5" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6M12 7h.01" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="10" width="14" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </>
  ),
  menu: (
    <>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </>
  ),
  plus: (
    <>
      <path d="M12 5v14M5 12h14" />
    </>
  ),
  route: (
    <>
      <circle cx="6" cy="18" r="2" />
      <circle cx="18" cy="6" r="2" />
      <path d="M8 18h2a2 2 0 0 0 2-2V8a2 2 0 0 1 2-2h2" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </>
  ),
  spark: (
    <>
      <path d="m12 3 1.2 4.2L17 9l-3.8 1.8L12 15l-1.2-4.2L7 9l3.8-1.8L12 3ZM5 15l.7 2.3L8 18l-2.3.7L5 21l-.7-2.3L2 18l2.3-.7L5 15Z" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V4m0 0L7 9m5-5 5 5M5 20h14" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </>
  ),
  warning: (
    <>
      <path d="M10.3 3.8 2.5 18a2 2 0 0 0 1.8 3h15.4a2 2 0 0 0 1.8-3L13.7 3.8a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4M12 17h.01" />
    </>
  ),
  x: (
    <>
      <path d="m6 6 12 12M18 6 6 18" />
    </>
  ),
};

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {iconPaths[name]}
    </svg>
  );
}

function Tooltip({ text }: { text: string }) {
  return (
    <span className="tooltip">
      <Icon name="info" size={15} />
      <span>{text}</span>
    </span>
  );
}

function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="logo" aria-label="GatorPath home">
      <span className="logo-mark">
        <Icon name="route" size={21} />
      </span>
      {!compact && (
        <span>
          Gator<span>Path</span>
        </span>
      )}
    </div>
  );
}

function Button({
  children,
  onClick,
  kind = "primary",
  icon,
  disabled = false,
  className = "",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  kind?: "primary" | "secondary" | "ghost";
  icon?: IconName;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button className={`button ${kind} ${className}`} onClick={onClick} disabled={disabled}>
      {icon && <Icon name={icon} />}
      {children}
    </button>
  );
}

function StatusBadge({
  type,
  children,
}: {
  type: "done" | "progress" | "planned" | "remaining" | "warning" | "ready";
  children: React.ReactNode;
}) {
  const icon =
    type === "warning"
      ? "warning"
      : type === "remaining"
        ? "clock"
        : type === "planned"
          ? "calendar"
          : "check";
  return (
    <span className={`status ${type}`}>
      <Icon name={icon} size={14} />
      {children}
    </span>
  );
}

function Header({
  screen,
  onHome,
  onBack,
  onStyle,
}: {
  screen: Screen;
  onHome: () => void;
  onBack?: () => void;
  onStyle: () => void;
}) {
  return (
    <header className="site-header">
      <div className="header-inner">
        <button className="brand-button" onClick={onHome}>
          <Logo />
        </button>
        {screen !== "landing" && (
          <div className="header-actions">
            {onBack && screen !== "app" && (
              <button className="header-link" onClick={onBack}>
                <Icon name="back" size={16} /> Back
              </button>
            )}
            {screen === "app" && (
              <a className="header-link ask-header" href={NAVIGATOR} target="_blank" rel="noreferrer">
                Ask an advisor
              </a>
            )}
            <button className="header-link" onClick={onHome}>
              Start over
            </button>
          </div>
        )}
        {screen === "landing" && (
          <div className="header-actions">
            <Button
              onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}
              kind="secondary"
            >
              How it works
            </Button>
          </div>
        )}
      </div>
    </header>
  );
}

const NAVIGATOR = "https://sfsu.campus.eab.com/";
function AdvisingNote() {
  return (
    <aside className="advising-note" aria-label="Advising">
      <Icon name="info" />
      <p>
        <b>GatorPath is a planning guide.</b> For any question about your plan, talk to an advisor
        before you register.
      </p>
      <a href={NAVIGATOR} target="_blank" rel="noreferrer">
        Book advising in Navigator <Icon name="arrow" size={14} />
      </a>
    </aside>
  );
}

const steps = ["Your record", "Your goals", "Your plan", "Your schedule"];
function Stepper({ current }: { current: number }) {
  return (
    <nav className="stepper" aria-label="Planning progress">
      {steps.map((step, i) => (
        <div
          className={`step ${i + 1 === current ? "active" : ""} ${i + 1 < current ? "complete" : ""}`}
          key={step}
        >
          <span className="step-dot">
            {i + 1 < current ? <Icon name="check" size={14} /> : i + 1}
          </span>
          <span>{step}</span>
          {i < steps.length - 1 && <i />}
        </div>
      ))}
    </nav>
  );
}

function Footer() {
  return (
    <footer>
      <Icon name="info" size={15} /> Unofficial student-built tool, not affiliated with SF State.
      Questions about your plan?{" "}
      <a href={NAVIGATOR} target="_blank" rel="noreferrer">
        Talk to an advisor in Navigator
      </a>
    </footer>
  );
}

function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({
    loading: true,
  });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true, error: undefined }));
    load().then(
      (data) => live && setState({ data, loading: false }),
      (e) => live && setState({ error: message(e), loading: false }),
    );
    return () => {
      live = false;
    };
  }, [...deps, attempt]); // eslint-disable-line react-hooks/exhaustive-deps
  return { ...state, retry: () => setAttempt((a) => a + 1) };
}

function Loading({ label }: { label: string }) {
  return (
    <div className="load-state" role="status">
      <span className="upload-orb spin">
        <Icon name="route" size={22} />
      </span>
      <strong>{label}</strong>
    </div>
  );
}

function ErrorCard({ text, retry }: { text: string; retry?: () => void }) {
  return (
    <div className="error-card" role="alert">
      <Icon name="warning" />
      <div>
        <b>That didn’t work.</b>
        <p>{text}</p>
        {retry && (
          <Button kind="secondary" onClick={retry}>
            Try again
          </Button>
        )}
        <p>
          Still stuck?{" "}
          <a href={NAVIGATOR} target="_blank" rel="noreferrer">
            Ask an advisor in Navigator
          </a>
        </p>
      </div>
    </div>
  );
}

const termLabel = (term?: string | null) =>
  term ? `${term[5].toUpperCase()}${term.slice(6)} ${term.slice(0, 4)}` : "";
/** Fall and spring terms around today, a calendar for the dropdowns: `back` past ones, `ahead` to come. */
function nearbyTerms(back: number, ahead: number) {
  const now = new Date();
  const fallNow = now.getMonth() >= 6;
  const index = now.getFullYear() * 2 + (fallNow ? 1 : 0);
  return Array.from({ length: back + ahead }, (_, i) => {
    const n = index - back + 1 + i;
    return `${Math.floor(n / 2)}-${n % 2 ? "fall" : "spring"}`;
  });
}

function Landing({ start }: { start: () => void }) {
  return (
    <main>
      <section className="hero">
        <div className="hero-copy">
          <h1>
            Plan your path to graduation in <em>5 minutes.</em>
          </h1>
          <p>
            Upload your DPR, tell us your goal, get a semester-by-semester plan and a
            clash-free schedule.
          </p>
          <div className="hero-actions">
            <Button onClick={start}>
              Start planning <Icon name="arrow" />
            </Button>
            <Button
              kind="secondary"
              onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}
            >
              How it works
            </Button>
          </div>
          <p className="micro-trust">
            <Icon name="lock" size={16} /> No account needed. Your DPR is processed, then discarded.
          </p>
        </div>
        <div className="plan-preview" aria-label="Sample degree plan">
          <div className="preview-top">
            <span>Sample plan</span>
          </div>
          <p className="preview-term">Spring 2029</p>
          <p>Estimated graduation</p>
          <div className="route-line">
            {["NOW", "F 27", "S 28", "F 28", "S 29"].map((x, i) => (
              <div key={x}>
                <span className={i === 0 ? "current" : i === 4 ? "finish" : ""}>
                  {i === 4 ? <Icon name="check" size={15} /> : ""}
                </span>
                <small>{x}</small>
              </div>
            ))}
          </div>
          <div className="preview-course">
            <div>
              <b>CSC 340</b>
              <small>Programming Methodology</small>
            </div>
            <span>3 units</span>
          </div>
          <div className="preview-course">
            <div>
              <b>MATH 324</b>
              <small>Probability and Statistics with Computing</small>
            </div>
            <span>3 units</span>
          </div>
        </div>
      </section>
      <section className="trust-row">
        <div>
          <Icon name="check" />
          <span>
            <b>Built from</b> the 2026–27 Bulletin
          </span>
        </div>
        <div>
          <Icon name="book" />
          <span>
            <b>100+ majors’</b> roadmaps
          </span>
        </div>
        <div>
          <Icon name="lock" />
          <span>
            <b>Your DPR</b> is never stored
          </span>
        </div>
      </section>
      <section className="how-section" id="how">
        <div className="section-heading">
          <h2>From DPR to a plan you can use.</h2>
          <p>No spreadsheets. No deciphering degree codes. Just three clear steps.</p>
        </div>
        <ol className="how-steps">
          <li>
            <b>Upload your DPR.</b> We read your completed courses, major requirements, and GE
            progress.
          </li>
          <li>
            <b>Pick your goal.</b> Tell us what you want to focus on and when you hope to finish.
          </li>
          <li>
            <b>Get your plan and schedule.</b> See every term, plus a next-semester schedule with
            class numbers.
          </li>
        </ol>
      </section>
      <section className="faq-section">
        <div>
          <h2>Questions, answered.</h2>
        </div>
        <div className="faq-list">
          <details open>
            <summary>
              Is GatorPath official?
              <Icon name="plus" />
            </summary>
            <p>
              No. GatorPath is a student-built planning aid. For any question about your degree,
              talk to an advisor:{" "}
              <a href={NAVIGATOR} target="_blank" rel="noreferrer">
                book one in Navigator
              </a>
              .
            </p>
          </details>
          <details>
            <summary>
              Is my data safe?
              <Icon name="plus" />
            </summary>
            <p>
              Your PDF is read in memory to find your courses, then discarded. It’s never written
              to disk, and your name and student ID are dropped as it’s read.
            </p>
          </details>
          <details>
            <summary>
              What’s a DPR?
              <Icon name="plus" />
            </summary>
            <p>
              Your Degree Progress Report shows completed courses and what your degree still
              requires.
            </p>
          </details>
        </div>
      </section>
    </main>
  );
}

function UploadPanel({ onSuccess }: { onSuccess: (result: ImportResult) => void }) {
  const [state, setState] = useState<"idle" | "uploading" | "error">("idle");
  const [problem, setProblem] = useState("");
  const picker = useRef<HTMLInputElement>(null);
  const fail = (text: string) => {
    setProblem(text);
    setState("error");
  };
  const begin = async (file?: File | null) => {
    if (!file) return;
    if (file.size > 15 * 1024 * 1024) return fail("That file is over 15 MB. Print just your DPR to PDF.");
    setState("uploading");
    try {
      onSuccess(await importDpr(file));
    } catch (e) {
      const unreadable = e instanceof EngineError && e.code === "unreadable_pdf";
      fail(unreadable ? "We couldn’t read that file. Is it your DPR, saved as a PDF?" : message(e));
    }
  };
  return (
    <div className="record-panel">
      {state === "idle" && (
        <button
          className="drop-zone"
          onClick={() => picker.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            begin(e.dataTransfer.files[0]);
          }}
        >
          <span className="upload-orb">
            <Icon name="upload" size={26} />
          </span>
          <strong>Drop your DPR PDF here</strong>
          <span>or click to choose a file</span>
          <small>PDF only · up to 15 MB</small>
        </button>
      )}
      <input
        ref={picker}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        aria-label="Your DPR PDF"
        onChange={(e) => {
          begin(e.target.files?.[0]);
          e.target.value = ""; // the same file can be picked again after an error
        }}
      />
      {state === "uploading" && (
        <div className="drop-zone loading-zone">
          <span className="upload-orb spin">
            <Icon name="file" size={26} />
          </span>
          <strong>Reading your DPR…</strong>
          <span>Finding courses and requirements</span>
          <div className="progress-bar">
            <i />
          </div>
          <small>Usually takes less than 30 seconds</small>
        </div>
      )}
      {state === "error" && <ErrorCard text={problem} retry={() => setState("idle")} />}
      <div className="privacy-note">
        <Icon name="lock" size={16} />
        <span>
          <b>Your DPR is never stored.</b> It’s read in memory to find your courses, then discarded.
        </span>
      </div>
      <details className="help-box">
        <summary>
          <span>
            <Icon name="info" /> How to get your DPR
          </span>
          <Icon name="chevron" />
        </summary>
        <ol>
          <li>
            Open <b>Student Center</b>
          </li>
          <li>
            Choose <b>Degree Progress Report</b>
          </li>
          <li>
            Click <b>Expand All</b>, then <b>View All</b> on every list that has it, then Print → Save
            as PDF
          </li>
        </ol>
        <div className="shot-row">
          {[1, 2, 3].map((n) => (
            <div className="shot" key={n}>
              <span>{n}</span>
              <div />
              <small>{n === 1 ? "Open DPR" : n === 2 ? "Expand All, View All" : "Save PDF"}</small>
            </div>
          ))}
        </div>
      </details>
      {DEMO && (
        <button
          className="demo-error"
          onClick={() =>
            fail("Some requirements were collapsed. Print your DPR again with “Expand All” turned on.")
          }
        >
          Preview upload error
        </button>
      )}
    </div>
  );
}

const GRADES = ["A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F", "CR", "NC", "W", "I"];
const IN_PROGRESS = "In progress";

function MajorSelect({ value, set }: { value: string; set: (id: string) => void }) {
  const programs = useLoad(getPrograms, []);
  if (programs.loading) return <Loading label="Loading majors…" />;
  if (programs.error) return <ErrorCard text={programs.error} retry={programs.retry} />;
  return (
    <label>
      Major
      <select value={value} onChange={(e) => set(e.target.value)}>
        {programs.data?.map((p) => (
          <option value={p.id} key={p.id}>
            {p.title}
          </option>
        ))}
      </select>
    </label>
  );
}

function TypedPanel({ done }: { done: (profile: Profile) => void }) {
  const [program, setProgram] = useState("bs-cs");
  const [rows, setRows] = useState<(Taken & { title: string })[]>([]);
  const [code, setCode] = useState("");
  const [grade, setGrade] = useState("A");
  const [term, setTerm] = useState(nearbyTerms(6, 0)[5]);
  const [state, setState] = useState<{ loading?: boolean; error?: string }>({});
  const add = async () => {
    setState({ loading: true });
    try {
      const course = await getCourse(code);
      setRows([...rows, { code: course.code, title: course.title, grade, term }]);
      setCode("");
      setState({});
    } catch (e) {
      setState({ error: message(e) });
    }
  };
  return (
    <div className="record-panel form-panel">
      <h3>Add your courses</h3>
      <MajorSelect value={program} set={setProgram} />
      <label>
        Course code
        <div className="search-field">
          <Icon name="search" />
          <input
            value={code}
            placeholder="CSC 215"
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && code && add()}
          />
        </div>
      </label>
      <div className="form-row">
        <label>
          Grade
          <select value={grade} onChange={(e) => setGrade(e.target.value)}>
            {[...GRADES, IN_PROGRESS].map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </label>
        <label>
          Term
          <select value={term} onChange={(e) => setTerm(e.target.value)}>
            {nearbyTerms(12, 0)
              .reverse()
              .map((t) => (
                <option value={t} key={t}>
                  {termLabel(t)}
                </option>
              ))}
          </select>
        </label>
      </div>
      <Button kind="secondary" icon="plus" onClick={add} disabled={!code || state.loading}>
        {state.loading ? "Finding it in the Bulletin…" : "Add course"}
      </Button>
      {state.error && <ErrorCard text={state.error} />}
      <div className="chips">
        {rows.map((r) => (
          <span key={r.code}>
            {r.code} · {r.grade}
            <button
              onClick={() => setRows(rows.filter((x) => x !== r))}
              aria-label={`Remove ${r.code}`}
            >
              <Icon name="x" size={13} />
            </button>
          </span>
        ))}
      </div>
      <Button
        disabled={!rows.length}
        onClick={() =>
          done({
            program,
            completed: rows
              .filter((r) => r.grade !== IN_PROGRESS)
              .map(({ code, grade, term }) => ({ code, grade, term })),
            in_progress: rows.filter((r) => r.grade === IN_PROGRESS).map((r) => r.code),
          })
        }
      >
        Review my record <Icon name="arrow" />
      </Button>
    </div>
  );
}

function NewStudentPanel({ done }: { done: (profile: Profile) => void }) {
  const terms = nearbyTerms(0, 4);
  const [program, setProgram] = useState("bs-cs");
  const [start, setStart] = useState(terms[0]);
  return (
    <div className="record-panel form-panel">
      <h3>Let’s start with the basics</h3>
      <MajorSelect value={program} set={setProgram} />
      <label>
        First term
        <select value={start} onChange={(e) => setStart(e.target.value)}>
          {terms.map((t) => (
            <option value={t} key={t}>
              {termLabel(t)}
            </option>
          ))}
        </select>
      </label>
      <Button onClick={() => done({ program, start_term: start })}>
        Continue <Icon name="arrow" />
      </Button>
    </div>
  );
}

function RecordScreen({ done }: { done: (profile: Profile, imported?: ImportResult) => void }) {
  const [method, setMethod] = useState<"upload" | "type" | "new">("upload");
  return (
    <main className="flow-page">
      <Stepper current={1} />
      <div className="flow-heading">
        <h1>Tell us what you’ve completed.</h1>
        <p>
          Choose the option that works best for you. You can review everything before we build your
          plan.
        </p>
      </div>
      <div className="method-grid">
        <button
          className={`method-card ${method === "upload" ? "selected" : ""}`}
          onClick={() => setMethod("upload")}
        >
          <span className="method-icon">
            <Icon name="upload" />
          </span>
          <span>
            <b>
              Upload my DPR <em>Recommended</em>
            </b>
            <small>Fastest and most accurate · about 2 minutes</small>
          </span>
          <i>{method === "upload" && <Icon name="check" size={14} />}</i>
        </button>
        <button
          className={`method-card ${method === "type" ? "selected" : ""}`}
          onClick={() => setMethod("type")}
        >
          <span className="method-icon">
            <Icon name="edit" />
          </span>
          <span>
            <b>Type my courses</b>
            <small>Add courses and grades yourself</small>
          </span>
          <i>{method === "type" && <Icon name="check" size={14} />}</i>
        </button>
        <button
          className={`method-card ${method === "new" ? "selected" : ""}`}
          onClick={() => setMethod("new")}
        >
          <span className="method-icon">
            <Icon name="user" />
          </span>
          <span>
            <b>I’m a new student</b>
            <small>Start with a major and first term</small>
          </span>
          <i>{method === "new" && <Icon name="check" size={14} />}</i>
        </button>
      </div>
      {method === "upload" && <UploadPanel onSuccess={(r) => done(r.profile, r)} />}
      {method === "type" && <TypedPanel done={done} />}
      {method === "new" && <NewStudentPanel done={done} />}
    </main>
  );
}

const NOT_ON_DPR = "not on the student's DPR"; // the engine's waived_by for a requirement the student left out
const isDone = (g: Group) => g.status === "satisfied" || g.status === "waived";
const universityGroups = (audit: Audit) => audit.groups.filter((g) => g.kind === "university");

function GeRequirementRows({
  groups,
  mode,
  plannedIn,
}: {
  groups: Group[];
  mode: "review" | "progress";
  plannedIn?: (group: Group) => string | undefined;
}) {
  return (
    <div className={`shared-ge-rows ${mode}`}>
      {groups.map((g) => {
        const planned = plannedIn?.(g);
        const done = isDone(g);
        const leftOut = g.waived_by === NOT_ON_DPR;
        return (
          <div className="shared-ge-row" key={g.id}>
            <div className="ge-area-name">
              <b>{g.title}</b>
              <small>{g.source}</small>
            </div>
            {mode === "review" ? (
              <span className={`binary-state ${done ? "met" : "not-yet"}`}>
                {done ? <Icon name="check" size={14} /> : <i />}
                {leftOut ? "Left out" : done ? "Met" : "Not yet"}
              </span>
            ) : (
              <StatusBadge type={done ? "done" : g.in_progress.length ? "progress" : planned ? "planned" : "remaining"}>
                {leftOut ? "Left out" : done ? "Done" : g.in_progress.length ? "In progress" : planned ? "Planned" : "Remaining"}
              </StatusBadge>
            )}
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
  const [showAll, setShowAll] = useState(false);
  const [editing, setEditing] = useState("");
  const audit = useLoad(() => getAudit(profile), [profile]);
  const programs = useLoad(getPrograms, []);
  const body = () => {
    if (audit.error) return <ErrorCard text={audit.error} retry={audit.retry} />;
    if (!audit.data) return <Loading label="Checking your record against the Bulletin…" />;
    const a = audit.data;
    const rows = profile.completed ?? [];
    const uni = universityGroups(a);
    const met = uni.filter(isDone).length;
    const todo = uni.filter((g) => !isDone(g));
    const left = profile.not_on_dpr ?? [];
    const notFound = imported?.cross_check.find((line) => line.startsWith("Not found on this DPR")) ?? "";
    const missing = uni.filter((g) => notFound.includes(g.title));
    const attention = [...new Set([...(imported?.cross_check ?? []), ...(imported?.warnings ?? [])])].filter(
      (line) => !missing.length || line !== notFound,
    );
    const gpa = profile.gpa ?? a.totals.gpa_sf_state?.value; // the DPR's, when there is one
    return (
      <>
        <div className="summary-card">
          <div>
            <small>Major</small>
            <b>{programs.data?.find((p) => p.id === profile.program)?.title ?? profile.program}</b>
          </div>
          <div>
            <small>
              Catalog year <Tooltip text="The Bulletin year whose degree rules apply to you." />
            </small>
            <b>{profile.catalog_year ?? a.catalog_year}</b>
          </div>
          <div>
            <small>
              Units <Tooltip text="A unit measures course credit; most classes are 3 units." />
            </small>
            <b>
              {a.totals.units.value} <span>/ {a.totals.units.needed}</span>
            </b>
          </div>
          {!!gpa && (
            <div>
              <small>GPA</small>
              <b>{gpa}</b>
            </div>
          )}
        </div>
        <SectionCard title="Completed courses" count={`${rows.length} courses`}>
          <div className="course-table">
            <div className="table-head">
              <span>Course</span>
              <span>Title</span>
              <span>Grade</span>
              <span>Term</span>
              <span />
            </div>
            {rows.map((r, i) => (
              <div className="table-row" key={`${r.code}-${r.term ?? i}`}>
                <b>{r.code}</b>
                <span>
                  {a.courses[r.code]?.title} {r.transfer && <em className="transfer">Transfer</em>}
                </span>
                {editing === r.code ? (
                  <select
                    autoFocus
                    aria-label={`Grade for ${r.code}`}
                    value={r.grade}
                    onBlur={() => setEditing("")}
                    onChange={(e) => {
                      setEditing("");
                      edit({
                        ...profile,
                        completed: rows.map((x) => (x === r ? { ...x, grade: e.target.value } : x)),
                      });
                    }}
                  >
                    {[...new Set([r.grade, ...GRADES])].map((g) => (
                      <option key={g}>{g}</option>
                    ))}
                  </select>
                ) : (
                  <span>{r.grade}</span>
                )}
                <span>{termLabel(r.term)}</span>
                <button aria-label={`Edit ${r.code}`} onClick={() => setEditing(r.code)}>
                  <Icon name="edit" size={15} />
                </button>
              </div>
            ))}
          </div>
        </SectionCard>
        {!!profile.in_progress?.length && (
          <SectionCard title="In progress" count={`${profile.in_progress.length} courses`}>
            <div className="in-progress-grid">
              {profile.in_progress.map((code) => (
                <CourseMini
                  code={code}
                  title={a.courses[code]?.title ?? ""}
                  status="In progress"
                  key={code}
                />
              ))}
            </div>
          </SectionCard>
        )}
        <section className="section-card ge-review-summary">
          <div className="ge-summary-head">
            <div>
              <h3>GE & university requirements</h3>
              <span>
                {met} of {uni.length} met
              </span>
            </div>
            <div
              className="ge-summary-progress"
              role="progressbar"
              aria-valuenow={met}
              aria-valuemin={0}
              aria-valuemax={uni.length}
              aria-label={`${met} of ${uni.length} requirements met`}
            >
              <i style={{ width: `${(met / Math.max(uni.length, 1)) * 100}%` }} />
            </div>
          </div>
          {!!(attention.length || missing.length) && (
            <div className="attention-list">
              <div className="attention-heading">
                <Icon name="warning" size={16} />
                <b>Check with an advisor</b>
              </div>
              {missing.map((g) => (
                <div className="attention-row" key={g.id}>
                  <span className="attention-dot" />
                  {left.includes(g.id) ? (
                    <p>
                      <b>{g.title}</b> isn’t on your DPR, so it’s left out of your plan. Confirm with an
                      advisor.{" "}
                      <button
                        onClick={() =>
                          edit({ ...profile, not_on_dpr: left.filter((id) => id !== g.id) })
                        }
                      >
                        Put it back
                      </button>
                    </p>
                  ) : (
                    <p>
                      <b>{g.title}</b> isn’t on your DPR, but it’s back in your plan.{" "}
                      <button onClick={() => edit({ ...profile, not_on_dpr: [...left, g.id] })}>
                        Leave it out
                      </button>
                    </p>
                  )}
                </div>
              ))}
              {attention.map((line) => (
                <div className="attention-row" key={line}>
                  <span className="attention-dot" />
                  <p>{line}</p>
                </div>
              ))}
              <p>
                <a href={NAVIGATOR} target="_blank" rel="noreferrer">
                  Ask an advisor in Navigator
                </a>
              </p>
            </div>
          )}
          {!!todo.length && (
            <p className="still-to-do">
              <b>Still to do</b> · we’ll fit these into your plan:{" "}
              {todo.map((g) => g.title).join(", ")}
            </p>
          )}
          <details className="all-ge-areas" onToggle={(e) => setShowAll(e.currentTarget.open)}>
            <summary>
              <span>
                {showAll ? "Hide" : "Show"} all {uni.length} requirements
              </span>
              <Icon name="chevron" />
            </summary>
            <GeRequirementRows groups={uni} mode="review" />
          </details>
        </section>
        <div className="flow-action">
          <Button onClick={next}>
            Looks right <Icon name="arrow" />
          </Button>
        </div>
      </>
    );
  };
  return (
    <main className="flow-page wide">
      <Stepper current={1} />
      <div className="flow-heading">
        <h1>Does this look right?</h1>
        <p>
          {imported ? "We found this in your DPR." : "This is what you told us."} If it doesn’t match
          your DPR, the DPR wins: fix a grade here, or ask an advisor.
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
        <h3>{title}</h3>
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
        <p>Your dates and load set your pace. Your focus stays next to your elective choices.</p>
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
              <h3>
                {goals.length ? "What do you want to focus on?" : "What are you interested in?"}
              </h3>
              <p>We’ll show it next to your elective choices, so you can pick with it in mind.</p>
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
              <h3>When do you want to graduate?</h3>
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
              <h3>
                Are you on an F-1 student visa?{" "}
                <Tooltip text="F-1 students need at least 12 units every fall and spring." />
              </h3>
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
              <h3>What is your math placement QR?</h3>
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
              <h3>What’s your first term?</h3>
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
const slotLabel = (slot: Slot, audit: Audit) =>
  slot.slot === "elective"
    ? "Free elective: any course"
    : (audit.groups.find((g) => g.id === slot.slot)?.title ?? slot.slot);

/** A slot of the plan to fill, or a pick to change. */
type Target = { group: string; term: string; title: string; replacing?: string };
type Pick = { group: string; term: string; code: string; readiness?: string; covers: string[] };

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
  undo?: () => void;
  note: string;
};

function Tabs({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  const items: [Tab, string, IconName][] = [
    ["plan", "Plan", "route"],
    ["progress", "Progress", "check"],
    ["electives", "Electives & GE", "book"],
    ["schedule", "Schedule", "calendar"],
  ];
  return (
    <nav className="app-tabs">
      {items.map(([key, label, icon]) => (
        <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
          <Icon name={icon} />
          {label}
        </button>
      ))}
    </nav>
  );
}

function ProblemPanel({ errors }: { errors: PlanError[] }) {
  return (
    <div className="plan-problem-panel" role="alert">
      <div>
        <Icon name="warning" />
        <span>
          <b>This plan has a problem</b>
          <small>Change your choices, or ask an advisor what to do.</small>
        </span>
      </div>
      {errors.map((e) => (
        <p key={e.message}>
          <span>{e.message}</span>
        </p>
      ))}
    </div>
  );
}

function AdvisorCards({ items }: { items: Advisor[] }) {
  return (
    <div className="advisor-list">
      {items.map((a) => (
        <div key={a.role}>
          <b>{a.who}</b>
          <p>
            {a.why.join(" ")} {a.how_to_book}
          </p>
          <a href={NAVIGATOR} target="_blank" rel="noreferrer">
            Book in Navigator <Icon name="arrow" size={12} />
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
  const graduation = (semesters.length === plan.semesters.length && plan.est_graduation_term) || lastTerm;
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
  const copyPlan = () => {
    const text = semesters
      .map(
        (s) =>
          `${termLabel(s.term)}: ${s.courses.map((c) => (isSlot(c) ? slotLabel(c, audit) : c)).join(", ")}`,
      )
      .join("\n");
    navigator.clipboard?.writeText(text).catch(() => {});
    toast("Plan copied to clipboard.");
  };
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
      {planState === "open" && (
        <div className="plan-status open">
          <span>
            <Icon name="clock" /> <b>{choicesLeft} choices left in your plan</b>
          </span>
          <button
            onClick={() =>
              document.getElementById("first-open-slot")?.scrollIntoView({ behavior: "smooth" })
            }
          >
            Make choices <Icon name="arrow" size={14} />
          </button>
        </div>
      )}
      {planState === "complete" && (
        <div className="plan-status complete">
          <span>
            <Icon name="check" /> <b>All choices made.</b> Take this plan to an advisor to confirm
            it before you register.
          </span>
          <a href={NAVIGATOR} target="_blank" rel="noreferrer">
            Book advising in Navigator <Icon name="arrow" size={14} />
          </a>
        </div>
      )}
      {planState === "problem" && <ProblemPanel errors={errors} />}
      {planState === "unreachable" && (
        <div className="plan-problem-panel unreachable">
          <div>
            <Icon name="clock" />
            <span>
              <b>{termLabel(pace?.graduate_by) || "That date"} isn’t reachable</b>
              <small>{pace?.why_not?.join(" ")}</small>
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
      <AdvisingNote />
      <section className="plan-hero">
        <div>
          {planState === "problem" ? (
            <h1>Fix the problem above to see your graduation date</h1>
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
              <option value="">Roadmap</option>
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
        {work.note && !work.busy && (
          <span className="what-if-result">
            {work.note}
            {work.undo && <button onClick={work.undo}>Undo</button>}
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
                            <em>
                              <Icon name="book" size={12} /> Bulletin p.{info[code]?.source_page}
                            </em>
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
            </summary>
            <ul>
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </details>
        )}
        <SectionCard title="Questions? Talk to an advisor">
          <AdvisorCards items={advisors} />
          <p className="advisor-fallback">
            For any question about your plan, book advising in{" "}
            <a href={NAVIGATOR} target="_blank" rel="noreferrer">
              Navigator
            </a>
            .
          </p>
        </SectionCard>
      </div>
      <div className="plan-actions">
        <Button kind="secondary" icon="download" onClick={() => window.print()}>
          Print for your advisor
        </Button>
        <Button kind="secondary" icon="copy" onClick={copyPlan}>
          Copy plan
        </Button>
        <a
          className="button primary"
          href={NAVIGATOR}
          target="_blank"
          rel="noreferrer"
          style={{ textDecoration: "none" }}
        >
          Book advising in Navigator <Icon name="arrow" />
        </a>
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
  const { audit, semesters } = work;
  const plannedTerm = (code: string) => semesters.find((s) => s.courses.includes(code))?.term;
  const plannedSlot = (g: Group) => {
    const term = semesters.find((s) => s.courses.some((c) => isSlot(c) && c.slot === g.id))?.term;
    return term && `Planned · ${termLabel(term)}`;
  };
  const buckets: [string, Group[]][] = [
    ["General Education", audit.groups.filter((g) => g.id.startsWith("ge_"))],
    ["SF State Studies", audit.groups.filter((g) => g.id.startsWith("sfss_"))],
    ["American Institutions", audit.groups.filter((g) => g.id.startsWith("ai_"))],
    [
      "Other university requirements",
      audit.groups.filter((g) => g.kind === "university" && !/^(ge|sfss|ai)_/.test(g.id)),
    ],
  ];
  const t = audit.totals;
  return (
    <div className="app-content">
      <div className="page-title">
        <h1>Your degree progress</h1>
        <p>See what’s done, planned, and still remaining.</p>
      </div>
      <AdvisingNote />
      <div className="ring-grid">
        <UnitBar value={t.units.value} total={t.units.needed ?? 120} label="Total units" />
        <UnitBar
          value={t.upper_division_units.value}
          total={t.upper_division_units.needed ?? 0}
          label="Upper-division units"
        />
        <div className="legend">
          <b>Status key</b>
          <span>
            <i className="dot done" /> <Icon name="check" /> Done
          </span>
          <span>
            <i className="dot progress" /> <Icon name="clock" /> In progress
          </span>
          <span>
            <i className="dot planned" /> <Icon name="calendar" /> Planned
          </span>
          <span>
            <i className="dot remaining" /> <Icon name="clock" /> Remaining
          </span>
        </div>
      </div>
      <SectionCard
        title="Degree requirements"
        count={`${t.units.value} of ${t.units.needed} units earned`}
      >
        <div className="requirement-list">
          {audit.groups
            .filter((g) => g.kind === "major")
            .map((g, i) => {
              const p = groupProgress(g);
              return (
                <details key={g.id} open={i === 0}>
                  <summary>
                    <span className="req-check" aria-hidden="true">
                      {p.percent === 100 ? <Icon name="check" /> : null}
                    </span>
                    <b>{g.title}</b>
                    <div className="mini-progress">
                      <i style={{ width: `${p.percent}%` }} />
                    </div>
                    <small>{p.label}</small>
                    <Icon name="chevron" />
                  </summary>
                  <div className="req-courses">
                    {g.counted.map((c) => (
                      <CourseStatus name={c} type="done" label="Done" key={c} />
                    ))}
                    {g.in_progress.map((c) => (
                      <CourseStatus name={c} type="progress" label="In progress" key={c} />
                    ))}
                    {g.remaining?.map((c) => (
                      <CourseStatus
                        name={c}
                        type="remaining"
                        label={plannedTerm(c) ? `Planned · ${termLabel(plannedTerm(c))}` : "Remaining"}
                        key={c}
                      />
                    ))}
                  </div>
                </details>
              );
            })}
          {buckets
            .filter(([, groups]) => groups.length)
            .map(([title, groups]) => {
              const met = groups.filter(isDone).length;
              const percent = (met / groups.length) * 100;
              return (
                <details key={title}>
                  <summary>
                    <span className="req-check" aria-hidden="true">
                      {percent === 100 ? <Icon name="check" /> : null}
                    </span>
                    <b>{title}</b>
                    <div className="mini-progress">
                      <i style={{ width: `${percent}%` }} />
                    </div>
                    <small>
                      {met} / {groups.length} done
                    </small>
                    <Icon name="chevron" />
                  </summary>
                  <GeRequirementRows groups={groups} mode="progress" plannedIn={plannedSlot} />
                </details>
              );
            })}
        </div>
      </SectionCard>
    </div>
  );
}
function UnitBar({ value, total, label }: { value: number; total: number; label: string }) {
  return (
    <div className="unit-bar">
      <div>
        <b>{label}</b>
        <span>
          {value} of {total}
        </span>
      </div>
      <div className="unit-bar-track" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={total} aria-label={label}>
        <i style={{ width: `${(value / total) * 100}%` }} />
      </div>
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
            <small>{r.id === "elective" ? "Units" : "Bulletin"}</small>
            <span>{audit.groups.find((g) => g.id === r.id)?.source ?? r.units}</span>
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

function ElectivesView({
  work,
  openPicker,
  goToProgress,
}: {
  work: Work;
  openPicker: (target: Target) => void;
  goToProgress: () => void;
}) {
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
  const done = audit.groups.filter(isDone);
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
          These are the requirements where you get to choose.
          {student.goal && student.goal !== "Undecided" ? ` Your focus: ${student.goal}.` : ""}
        </p>
      </div>
      <AdvisingNote />
      {!check.valid && <ProblemPanel errors={check.errors} />}
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
      {!!done.length && <details className="already-done">
        <summary>
          <span>
            <Icon name="check" /> Already done
          </span>
          <span>
            {done.length} requirements <Icon name="chevron" />
          </span>
        </summary>
        <div>
          <p>{done.map((g) => g.title).join(", ")}</p>
          <button onClick={goToProgress}>
            See completed requirements in Progress <Icon name="arrow" size={14} />
          </button>
        </div>
      </details>}
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
const when = (s: Section) =>
  s.meetings.map((m) => [m.days, m.time, m.where].filter(Boolean).join(" ")).join("; ") || s.mode;
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
  const result = useLoad(() => getSections(first.term, codes), [first.term, codes.join()]);
  const [preview, setPreview] = useState<"" | "ready" | "not-offered" | "unpublished" | "no-fit" | "full">("");
  if (!codes.length) return <div className="app-content"><p>Choose this term’s courses first.</p></div>;
  if (result.error) return <div className="app-content"><ErrorCard text={result.error} retry={result.retry} /></div>;
  if (!result.data) return <div className="app-content"><Loading label={`Finding ${label} sections…`} /></div>;
  const r = result.data;
  const classes = Object.entries(r.schedule ?? {}).map(([code, numbers]) => ({
    code,
    picked: r.sections[code].filter((s) => numbers.includes(s.class_nbr)),
    others: r.sections[code].filter((s) => !numbers.includes(s.class_nbr)),
  }));
  const classNumbers = Object.values(r.schedule ?? {}).flat();
  const derived =
    r.schedule === null && r.always_clash.length
      ? "no-fit"
      : r.schedule === null && !Object.keys(r.sections).length
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
  const blocks = classes.flatMap((c, i) =>
    c.picked.flatMap((s) =>
      s.meetings.flatMap((m) => {
        const time = hours(m);
        return time && m.days
          ? m.days.split(" ").map((day) => ({ c, i, s, m, time, day }))
          : [];
      }),
    ),
  );
  return (
    <div className="app-content">
      <div className="schedule-title">
        <div>
          <h1>Your {label} schedule</h1>
          <p>One clash-free combination based on your plan.</p>
        </div>
        <Button
          disabled={!classNumbers.length}
          onClick={() => {
            navigator.clipboard?.writeText(classNumbers.join(", ")).catch(() => {});
            toast(`${classNumbers.length} class numbers copied: paste them into Student Center`);
          }}
          icon="copy"
        >
          Copy all class numbers
        </Button>
      </div>
      <AdvisingNote />
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
                One of {r.sets} {r.sets === 1 ? "schedule" : "schedules"} without time clashes
              </b>
            </div>
          </div>
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
                      className={`cal-block c${b.i % 3}`}
                      key={`${b.s.class_nbr}${b.m.time}${b.day}`}
                      style={{
                        top: (b.time.start - 8) * 52 + 1,
                        height: (b.time.end - b.time.start) * 52 - 3,
                        left: `calc(${CALENDAR_DAYS.findIndex(([, code]) => code === b.day)} * 20% + 4px)`,
                      }}
                    >
                      <b>
                        {b.c.code} {b.s.component !== "LEC" ? b.s.component : ""}
                      </b>
                      <span>{b.m.time}</span>
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
                      <span key={`${b.s.class_nbr}${b.m.time}`}>
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
              return (
                <article className="section-detail" key={c.code}>
                  <div className="section-main">
                    <span>
                      <b>{c.code}</b>
                      <StatusBadge type={main.seats_open ? "ready" : "warning"}>{seats(main)}</StatusBadge>
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
                      {main.instructor ? ` · ${main.instructor}` : ""}
                      {Object.entries(main.rate_my_professors ?? {}).map(([name, link]) => (
                        <span key={name}>
                          {" · "}
                          <a href={link} target="_blank" rel="noreferrer">
                            Rate My Professors (student opinions)
                          </a>
                        </span>
                      ))}
                    </small>
                    {!!c.others.length && (
                      <details className="other-sections">
                        <summary>
                          Other sections <Icon name="chevron" />
                        </summary>
                        {c.others.map((o) => (
                          <div className={o.clashes_with?.length ? "disabled" : ""} key={o.class_nbr}>
                            <span>
                              Section {o.section} · {when(o)} · #{o.class_nbr}
                            </span>
                            <small>
                              {o.clashes_with?.length
                                ? `Clashes with ${o.clashes_with.join(", ")}`
                                : "Fits instead"}
                            </small>
                          </div>
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
              <Icon name="clock" /> Seats and rooms as of {new Date(r.scraped_at).toLocaleDateString()}.
              Confirm in{" "}
              <a href={CLASS_SEARCH} target="_blank" rel="noreferrer">
                Class Search
              </a>{" "}
              before registering.
            </div>
          )}
          {r.warnings
            .filter((w) => !w.startsWith("Class Search as of"))
            .map((w) => (
              <div className="schedule-note" key={w}>
                <Icon name="warning" /> {w}
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

function FreeCourse({ choose }: { choose: (code: string) => void }) {
  const [code, setCode] = useState("");
  const [state, setState] = useState<{ loading?: boolean; error?: string }>({});
  const add = async () => {
    setState({ loading: true });
    try {
      choose((await getCourse(code)).code);
    } catch (e) {
      setState({ error: message(e) });
    }
  };
  return (
    <div className="record-panel form-panel">
      <label>
        Course code
        <div className="search-field">
          <Icon name="search" />
          <input
            autoFocus
            value={code}
            placeholder="ART 101"
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && code && add()}
          />
        </div>
      </label>
      <Button onClick={add} disabled={!code || state.loading}>
        {state.loading ? "Finding it in the Bulletin…" : "Add to my plan"}
      </Button>
      {state.error && <ErrorCard text={state.error} />}
    </div>
  );
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
          {reason}
        </p>
      ))}
      {o.ready_by && (
        <p className="check-reason">
          <Icon name="clock" size={13} />
          Opens up in {termLabel(o.ready_by)}
        </p>
      )}
      {o.note && <p className="check-reason">{o.note}</p>}
      <p>{offeredText(o.offered)}</p>
      {o.not_offered && (
        <p className="rare-note">
          <Icon name="warning" size={13} /> {o.not_offered}
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
  const free = target.group === "elective";
  const result = useLoad(
    () =>
      free
        ? Promise.resolve(null)
        : getElectives(work.student, target.group, { semesters: work.semesters }, target.term),
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
        {free && <FreeCourse choose={(code) => choose(code)} />}
        {result.loading && <Loading label="Finding courses that fit…" />}
        {result.error && <ErrorCard text={result.error} retry={result.retry} />}
        {result.data?.approval && (
          <p className="check-reason">
            <Icon name="warning" size={13} />
            {result.data.approval}. Ask your advisor in Navigator which courses count.
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

function AppWorkspace({ profile, built }: { profile: Profile; built: Built }) {
  const [tab, setTab] = useState<Tab>("plan");
  const [picker, setPicker] = useState<Target | null>(null);
  const [course, setCourse] = useState("");
  const [toast, setToast] = useState("");
  const [state, setState] = useState({
    options: built.options,
    plan: built.plan,
    semesters: built.plan.semesters,
    check: built.plan.check ?? ({ valid: true, errors: [] } as Checked),
    info: built.plan.courses ?? {},
    picks: [] as Pick[],
  });
  const [busy, setBusy] = useState("");
  const [failed, setFailed] = useState("");
  const [note, setNote] = useState("");
  const [previous, setPrevious] = useState<typeof state | null>(null);
  const student = { ...profile, ...state.options };
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
      setNote(done(next));
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
        const plan = await buildPlan(profile, options);
        if (plan.needs_input) throw new Error("That change needs more about you: go back to your goals.");
        return {
          options,
          plan,
          semesters: plan.semesters,
          check: plan.check ?? { valid: true, errors: [] },
          info: plan.courses ?? {},
          picks: [],
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
  const work: Work = {
    ...state,
    student,
    audit: built.audit,
    busy,
    failed,
    whatIf,
    applyFold,
    note,
    undo: previous
      ? () => {
          setState(previous);
          setPrevious(null);
          setNote("");
        }
      : undefined,
  };
  const why = state.semesters.find((s) => s.why?.[course])?.why?.[course];
  return (
    <>
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
        <ElectivesView work={work} openPicker={setPicker} goToProgress={() => setTab("progress")} />
      )}
      {tab === "schedule" && (
        <ScheduleView work={work} openPlan={() => setTab("plan")} toast={showToast} />
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
    </>
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
      <Header
        screen={screen}
        onHome={home}
        onBack={screen !== "landing" ? back : undefined}
        onStyle={() => setStyle(true)}
      />
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
      {screen === "app" && profile && built && <AppWorkspace profile={profile} built={built} />}
      {style && <StyleGuide close={() => setStyle(false)} />}
      <Footer />
    </div>
  );
}
