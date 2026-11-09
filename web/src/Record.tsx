import { useEffect, useRef, useState } from "react";
import {
  EngineError,
  getAudit,
  getCourse,
  getPrograms,
  searchCourses,
  importDpr,
  message,
  type Audit,
  type Choice,
  type CourseMatch,
  type Group,
  type ImportResult,
  type Profile,
  type Semester,
  type Slot,
  type Taken,
} from "./api";
import { FloatingCard } from "./FloatingCard";
import { NOT_ON_DPR, countSection, markOf, plainWarning, termLabel, unitText, warnedGroups, type Mark } from "./logic";
import { StatusMark, WORD } from "./StatusMark";
import { Button, DEMO, ErrorCard, Icon, Loading, Stepper, nearbyTerms, useLoad } from "./ui";

function UploadPanel({ onSuccess }: { onSuccess: (result: ImportResult) => void }) {
  const [state, setState] = useState<"idle" | "uploading" | "error" | "choose">("idle");
  const [problem, setProblem] = useState("");
  const [choices, setChoices] = useState<Choice[]>([]);
  const [pick, setPick] = useState("");
  const picker = useRef<HTMLInputElement>(null);
  const file = useRef<File | null>(null); // kept in the tab, to read again as the major the student picks
  const fail = (text: string) => {
    setProblem(text);
    setState("error");
  };
  const begin = async (chosen?: File | null, program?: string) => {
    if (!chosen) return;
    if (chosen.size > 15 * 1024 * 1024) return fail("That file is over 15 MB. Print just your DPR to PDF.");
    file.current = chosen;
    setState("uploading");
    try {
      onSuccess(await importDpr(chosen, program));
    } catch (e) {
      if (e instanceof EngineError && e.code === "unknown_program" && e.choices.length) {
        setProblem(e.message);
        setChoices(e.choices);
        setPick(e.choices[0].id);
        return setState("choose");
      }
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
      {state === "choose" && (
        <div className="form-panel choose-major">
          <h2>Which major is this DPR for?</h2>
          <p>{problem}</p>
          <label>
            Major
            <select value={pick} onChange={(e) => setPick(e.target.value)}>
              {choices.map((c) => (
                <option value={c.id} key={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </label>
          <div className="choose-actions">
            <Button onClick={() => begin(file.current, pick)}>Read my DPR as this major</Button>
            <Button kind="ghost" onClick={() => setState("idle")}>
              Choose another file
            </Button>
          </div>
        </div>
      )}
      <section className="howto" aria-labelledby="howto-title">
        <h2 id="howto-title">How to get your DPR</h2>
        <div className="howto-body">
          <video className="howto-video" controls playsInline preload="none" poster="/dpr-video-poster.jpg" aria-label="How to get your DPR from Student Center">
            <source src="/how-to-get-your-dpr.mp4" type="video/mp4" />
            Your browser can’t play this video. Follow the steps beside it to save your DPR as a PDF.
          </video>
          <ol>
            <li>
              Open <b>Student Center</b>
            </li>
            <li>
              Choose <b>Degree Progress Report</b>
            </li>
            <li>
              Click <b>Expand All</b>, then <b>View All</b> on every list that has it
            </li>
            <li>
              <b>Print</b>, then <b>Save as PDF</b>
            </li>
          </ol>
        </div>
      </section>
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
const RECORD_KEY = "gatorpath-record-v1";
function recordDraft(): Record<string, unknown> {
  try { return JSON.parse(sessionStorage.getItem(RECORD_KEY) || "{}") || {}; } catch { return {}; }
}

const courseCache = new Map<string, Promise<CourseMatch[]>>();
function CourseSearch({ code, setCode, add }: { code: string; setCode: (code: string) => void; add: () => void }) {
  const subject = /^[A-Za-z]{2,5}/.exec(code.trim())?.[0].toUpperCase() ?? "";
  const [found, setFound] = useState<{ subject: string; rows: CourseMatch[] }>({ subject: "", rows: [] });
  const [selected, setSelected] = useState<CourseMatch | null>(null);
  const [open, setOpen] = useState(true);
  const [active, setActive] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => { if (!code) { setSelected(null); setOpen(true); } }, [code]);
  useEffect(() => {
    if (!subject) return;
    let cancelled = false;
    let pending = courseCache.get(subject);
    if (!pending) {
      pending = searchCourses(subject);
      courseCache.set(subject, pending);
      pending.catch(() => courseCache.delete(subject));
    }
    pending.then((rows) => {
      if (!cancelled) { setFound({ subject, rows }); setError(""); }
    }).catch(() => { if (!cancelled) setError("Search is unavailable. You can still enter a course code."); });
    return () => { cancelled = true; };
  }, [subject]);
  const prefix = code.toUpperCase().replace(/\s/g, "");
  const results = found.subject === subject && subject
    ? found.rows.filter((course) => course.code.replace(/\s/g, "").startsWith(prefix)) : [];
  const choose = (course: CourseMatch) => {
    setSelected(course);
    setCode(course.code);
    setOpen(false);
  };
  return (
    <div className="course-search">
      <div className="search-field">
        <Icon name="search" />
        <input
          id="course-code"
          value={code}
          placeholder="Try CSC or CSC 215"
          aria-expanded={open && !!results.length}
          aria-controls="course-suggestions"
          onFocus={() => { if (!selected) setOpen(true); }}
          onChange={(e) => { setSelected(null); setCode(e.target.value); setActive(0); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" && open && results.length) { e.preventDefault(); setActive((active + 1) % results.length); }
            if (e.key === "ArrowUp" && open && results.length) { e.preventDefault(); setActive((active - 1 + results.length) % results.length); }
            if (e.key === "Escape") setOpen(false);
            if (e.key === "Enter" && code) {
              e.preventDefault();
              if (open && results.length && !selected) choose(results[active]);
              else add();
            }
          }}
        />
      </div>
      <div className="course-search-results" id="course-suggestions">
        {selected && !open ? (
          <div className="course-selected">
            <span>Selected course</span>
            <strong>{selected.code} · {selected.title}</strong>
            <p>{selected.description || "No description in the Bulletin."}</p>
          </div>
        ) : results.length && open ? (
          <ul className="course-suggestions" aria-label="Matching courses">
            {results.map((course, index) => (
              <li key={course.code}>
                <button type="button" className={index === active ? "active" : ""} onClick={() => choose(course)}>
                  <strong>{course.code} · {course.title}</strong>
                  <small>{course.description ? `${course.description.slice(0, 160)}${course.description.length > 160 ? "…" : ""}` : "No description in the Bulletin."}</small>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="course-search-hint" role="status">
            {error || (subject && found.subject !== subject ? "Finding courses…" : subject && !open ? "Focus the field to see matches." : subject ? "No matching courses. Try another code." : "Enter a subject like CSC to browse its courses.")}
          </p>
        )}
      </div>
    </div>
  );
}

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

function TypedPanel({ done, back }: { done: (profile: Profile) => void; back: () => void }) {
  const [draft] = useState(recordDraft);
  const [program, setProgram] = useState(typeof draft.program === "string" ? draft.program : "bs-cs");
  const [rows, setRows] = useState<(Taken & { title: string })[]>(Array.isArray(draft.rows) ? draft.rows : []);
  const [code, setCode] = useState(typeof draft.code === "string" ? draft.code : "");
  const [grade, setGrade] = useState(typeof draft.grade === "string" ? draft.grade : "A");
  const [term, setTerm] = useState(typeof draft.term === "string" ? draft.term : nearbyTerms(6, 0)[5]);
  useEffect(() => { try { sessionStorage.setItem(RECORD_KEY, JSON.stringify({ ...recordDraft(), program, rows, code, grade, term })); } catch { /* storage unavailable */ } }, [program, rows, code, grade, term]);
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
      <h2>Add your courses</h2>
      <MajorSelect value={program} set={setProgram} />
      <div className="course-search-field">
        <label htmlFor="course-code">Course code</label>
        <CourseSearch code={code} setCode={setCode} add={add} />
      </div>
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
      <div className="flow-action">
        <Button kind="ghost" onClick={back}><Icon name="back" size={16} /> Back</Button>
        <Button disabled={!rows.length} onClick={() => done({
          program,
          completed: rows.filter((r) => r.grade !== IN_PROGRESS).map(({ code, grade, term }) => ({ code, grade, term })),
          in_progress: rows.filter((r) => r.grade === IN_PROGRESS).map((r) => r.code),
        })}>Next <Icon name="arrow" /></Button>
      </div>
    </div>
  );
}

function NewStudentPanel({ done, back }: { done: (profile: Profile) => void; back: () => void }) {
  const terms = nearbyTerms(0, 4);
  const [draft] = useState(recordDraft);
  const [program, setProgram] = useState(typeof draft.newProgram === "string" ? draft.newProgram : "bs-cs");
  const [start, setStart] = useState(typeof draft.start === "string" ? draft.start : terms[0]);
  useEffect(() => { try { sessionStorage.setItem(RECORD_KEY, JSON.stringify({ ...recordDraft(), newProgram: program, start })); } catch { /* storage unavailable */ } }, [program, start]);
  return (
    <div className="record-panel form-panel">
      <h2>Let’s start with the basics</h2>
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
      <div className="flow-action">
        <Button kind="ghost" onClick={back}><Icon name="back" size={16} /> Back</Button>
        <Button onClick={() => done({ program, start_term: start })}>Next <Icon name="arrow" /></Button>
      </div>
    </div>
  );
}

export function RecordScreen({ done, back }: { done: (profile: Profile, imported?: ImportResult) => void; back: () => void }) {
  const [method, setMethod] = useState<"upload" | "type" | "new">(() => {
    const value = recordDraft().method;
    return value === "type" || value === "new" ? value : "upload";
  });
  useEffect(() => { try { sessionStorage.setItem(RECORD_KEY, JSON.stringify({ ...recordDraft(), method })); } catch { /* storage unavailable */ } }, [method]);
  return (
    <main className="flow-page">
      <Stepper current={1} />
      <div className="flow-heading">
        <h1>Tell us what you’ve completed.</h1>
        <p>Choose one. You’ll check everything before we build your plan.</p>
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
            <small>Fastest and most accurate</small>
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
      {method === "type" && <TypedPanel done={done} back={back} />}
      {method === "new" && <NewStudentPanel done={done} back={back} />}
      {method === "upload" && <div className="flow-action"><Button kind="ghost" onClick={back}><Icon name="back" size={16} /> Back</Button></div>}
    </main>
  );
}

/** Edit's card: change a grade, finish a course in progress (no `row`), or take the course off the record. */
function CourseEdit({
  profile,
  code,
  row,
  edit,
  close,
  locked,
}: {
  profile: Profile;
  code: string;
  row?: Taken;
  edit: (profile: Profile) => void;
  close: () => void;
  locked?: boolean;
}) {
  const rows = profile.completed ?? [];
  const going = profile.in_progress ?? [];
  return (
    <fieldset className="form-panel rq-card" disabled={locked}>
      <h3>{code}</h3>
      <label>
        {row ? "Grade" : "Status"}
        <select
          value={row?.grade ?? ""}
          onChange={(e) => {
            if (row) return edit({ ...profile, completed: rows.map((x) => (x === row ? { ...x, grade: e.target.value } : x)) });
            edit({
              ...profile,
              in_progress: going.filter((x) => x !== code),
              completed: [...rows, { code, grade: e.target.value, term: nearbyTerms(1, 0)[0] }],
            });
            close();
          }}
        >
          {row ? (
            [...new Set([row.grade, ...GRADES])].map((g) => <option key={g}>{g}</option>)
          ) : (
            <>
              <option value="">In progress</option>
              {GRADES.map((g) => (
                <option value={g} key={g}>
                  Finished: {g}
                </option>
              ))}
            </>
          )}
        </select>
      </label>
      <Button
        kind="secondary"
        icon="x"
        onClick={() => {
          edit(
            row
              ? { ...profile, completed: rows.filter((x) => x !== row) }
              : { ...profile, in_progress: going.filter((x) => x !== code) },
          );
          close();
        }}
      >
        Remove from my record
      </Button>
    </fieldset>
  );
}

/** "+ Add a course": one the DPR doesn't show, or one finished since. */
function AddCourse({ profile, edit, locked }: { profile: Profile; edit: (profile: Profile) => void; locked?: boolean }) {
  const rows = profile.completed ?? [];
  const going = profile.in_progress ?? [];
  const [code, setCode] = useState("");
  const [grade, setGrade] = useState("A");
  const [term, setTerm] = useState(nearbyTerms(1, 0)[0]);
  const [state, setState] = useState<{ loading?: boolean; error?: string; added?: string }>({});
  const add = async () => {
    setState({ loading: true });
    try {
      const c = (await getCourse(code)).code;
      edit(
        grade === IN_PROGRESS
          ? { ...profile, in_progress: [...going.filter((x) => x !== c), c] }
          : {
              ...profile,
              completed: [...rows.filter((r) => !(r.code === c && r.term === term)), { code: c, grade, term }],
              in_progress: going.filter((x) => x !== c),
            },
      );
      setCode("");
      setState({ added: c });
    } catch (e) {
      setState({ error: message(e) });
    }
  };
  return (
    <fieldset className="form-panel rq-card add-course-card" disabled={locked}>
      <div className="add-course-heading">
        <h3>Add a course</h3>
        <p>Find it in the Bulletin, then add it to your record.</p>
      </div>
      <div className="course-search-field">
        <label htmlFor="course-code">Course code</label>
        <CourseSearch code={code} setCode={setCode} add={add} />
      </div>
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
          <select value={term} disabled={grade === IN_PROGRESS} onChange={(e) => setTerm(e.target.value)}>
            {nearbyTerms(12, 0)
              .reverse()
              .map((x) => (
                <option value={x} key={x}>
                  {termLabel(x)}
                </option>
              ))}
          </select>
        </label>
      </div>
      <div className="add-course-footer">
        <Button icon="plus" onClick={add} disabled={!/\d/.test(code) || state.loading}>
          {state.loading ? "Checking course…" : "Add to my record"}
        </Button>
      </div>
      {state.error && <ErrorCard text={state.error} />}
      <p role="status" className="rq-added">
        {state.added && `Added ${state.added}.`}
      </p>
    </fieldset>
  );
}

const NOT_FOUND = "Not found on this DPR"; // the cross-check line for requirements the DPR doesn't list
const SECTIONS: [string, (g: Group) => boolean][] = [
  ["General Education", (g) => g.id.startsWith("ge_")],
  ["SF State Studies", (g) => g.id.startsWith("sfss_")],
  ["American Institutions", (g) => g.id.startsWith("ai_")],
  ["University requirements", (g) => g.kind === "university" && !/^(ge|sfss|ai)_/.test(g.id)],
  ["Major", (g) => g.kind === "major"],
];
const MARKS: Mark[] = ["complete", "progress", "planned", "incomplete", "exception", "warning"];
const plannedText = (term?: string) => (term ? `Planned · ${termLabel(term)}` : "Planned");

/** One course line under a requirement: a `row` or `going` makes it editable. */
type Line = { key: string; code: string; units?: number | string; when: string; grade?: string; row?: Taken; going?: boolean };

/** GatorPath's reading of the record, in the DPR's order: every requirement from the audit, every disagreement with
 * the DPR as a Warning. Sections start closed. With `withPlan` (the audit of withPlanned(profile, semesters)) it also
 * counts what the plan completes and says when a course is planned. */
export function RequirementsView({
  profile,
  imported,
  audit,
  withPlan,
  semesters,
  edit,
  locked,
  leave,
}: {
  profile: Profile;
  imported: ImportResult | null;
  audit: Audit;
  withPlan?: Audit;
  semesters?: Semester[]; // the plan's terms, for "Planned · Spring 2027"
  edit: (profile: Profile) => void;
  locked?: boolean; // the chat is changing the plan: an edit now would be lost
  leave?: { label: string; go: () => void };
}) {
  const [editing, setEditing] = useState<string | null>(null); // one card at a time: a line's key, or "add"
  const close = () => setEditing(null);
  const toggle = (key: string) => setEditing(editing === key ? null : key);
  const warned = warnedGroups(profile, imported);
  const rows = profile.completed ?? [];
  const going = profile.in_progress ?? [];
  const left = profile.not_on_dpr ?? [];
  const excluded = audit.groups.filter((g) => g.waived_by === NOT_ON_DPR).length;
  const units = (code: string) => audit.courses[code]?.units;
  const plannedIn = (test: (c: string | Slot) => boolean) => semesters?.find((s) => s.courses.some(test))?.term;

  const line = (l: Line) => (
    <div className="rq-course" key={l.key}>
      <b className="rq-code">{l.code}</b>
      <span className="rq-title">{audit.courses[l.code]?.title}</span>
      <span className="rq-units">{l.units != null && unitText(l.units)}</span>
      <span className={`rq-when ${l.going ? "going" : ""}`}>{l.when}</span>
      <b className="rq-grade">{l.grade}</b>
      {(l.row || l.going) && (
        <>
          <button type="button" className="rq-link rq-edit" aria-expanded={editing === l.key} disabled={locked} onClick={() => toggle(l.key)}>
            Edit<span className="sr-only"> {l.code}</span>
          </button>
          {editing === l.key && (
            <FloatingCard label={`Edit ${l.code}`} onClose={close}>
              <CourseEdit profile={profile} code={l.code} row={l.row} edit={edit} close={close} locked={locked} />
            </FloatingCard>
          )}
        </>
      )}
    </div>
  );
  const rowLine = (where: string, r: Taken, i: number): Line => ({
    key: `${where}:${r.code}:${r.term ?? i}`,
    code: r.code,
    units: units(r.code),
    when: r.transfer ? "Transfer" : termLabel(r.term),
    grade: r.grade,
    row: r,
  });
  const taken = (where: string, code: string): Line[] => {
    const mine = rows.filter((r) => r.code === code);
    return mine.length
      ? mine.map((r, i) => rowLine(where, r, i))
      : [{ key: `${where}:${code}`, code, units: units(code), when: "Met on your DPR" }]; // a substitution (dpr_met)
  };
  const inProgress = (where: string, code: string): Line => ({
    key: `${where}:${code}:going`, code, units: units(code), when: "In progress", going: true,
  });

  const requirement = (g: Group) => {
    const projected = withPlan?.groups.find((x) => x.id === g.id);
    const mark = markOf(g, warned.has(g.id), projected?.status === "satisfied" || projected?.status === "waived");
    const warnings = imported?.warnings_by_group?.[g.id] ?? [];
    const missing = left.includes(g.id) || warnings.some((w) => w.startsWith(NOT_FOUND));
    const planned = (projected?.counted ?? []).filter(
      (c) => !g.counted.includes(c) && !g.in_progress.includes(c),
    );
    const needed = (g.remaining ?? []).filter((c) => !planned.includes(c));
    const slot = plannedIn((c) => typeof c !== "string" && c.slot === g.id);
    const ongoing = g.in_progress.reduce((n, c) => n + (Number(units(c)) || 0), 0); // the DPR's "taken" counts these
    const short = (g.units_needed ?? 0) - (g.units_done ?? 0) - ongoing;
    const details = [
      // an import's ge_done is every GE area the DPR shows done; typed, it is only transfer, AP or IB credit
      g.met_by === "ge_done" && (imported ? "Met on your DPR" : "Met by transfer credit"),
      g.status === "unparsed" && "GatorPath can’t check this one. Check it on your DPR.",
      !!g.units_needed &&
        `${unitText(g.units_needed)} required, ${(g.units_done ?? 0) + ongoing} taken${short > 0 ? `, ${short} needed` : ""}`,
      ...(imported?.notes_by_group?.[g.id] ?? (g.waived_by && g.waived_by !== NOT_ON_DPR ? [`Waived: ${g.waived_by}`] : [])),
      needed.length > 0 && `Needed: ${needed.join(", ")}`,
      slot && plannedText(slot),
    ].filter((x): x is string => !!x);
    return (
      <div className="rq-req" key={g.id}>
        <div className="rq-req-head">
          <span aria-hidden="true">
            <StatusMark mark={mark} />
          </span>
          <b>{g.title}</b>
          <span className={`rq-word ${mark}`}>{WORD[mark]}</span>
        </div>
        {details.map((d, i) => (
          <p className="rq-detail" key={i}>
            {d}
          </p>
        ))}
        {missing && (
          <p className="rq-note">
            <span>
              {left.includes(g.id)
                ? "Your DPR doesn’t list this, so it’s left out of your plan. Confirm with an advisor that you don’t need it."
                : "Your DPR doesn’t list this, but it’s back in your plan."}
            </span>
            <button
              type="button"
              className="rq-link"
              disabled={locked}
              onClick={() =>
                edit({ ...profile, not_on_dpr: left.includes(g.id) ? left.filter((x) => x !== g.id) : [...left, g.id] })
              }
            >
              {left.includes(g.id) ? "Put it back" : "Leave it out"}
            </button>
          </p>
        )}
        {warnings
          .filter((w) => !w.startsWith(NOT_FOUND))
          .map((w, i) => (
            <p className="rq-note" key={i}>
              {plainWarning(w)}
            </p>
          ))}
        {g.met_by !== "ge_done" && g.counted.flatMap((c) => taken(g.id, c)).map(line)}
        {g.in_progress.map((c) => line(inProgress(g.id, c)))}
        {planned.map((c) =>
          line({ key: `${g.id}:${c}:planned`, code: c, units: units(c), when: plannedText(plannedIn((x) => x === c)) }),
        )}
      </div>
    );
  };

  // Every course on the record shows somewhere, so each can be edited: under a requirement, in the DPR's own
  // "Courses Not Used" (editable when the record has that row), or with the other courses
  const shown = new Set(audit.groups.flatMap((g) => [...g.counted, ...g.in_progress]));
  const listed = new Set<Taken | string>();
  const notUsed = (imported?.not_used ?? []).map((r, i): Line => {
    const mine = rows.find((x) => x.code === r.code && (x.term ?? null) === (r.term ?? null));
    if (mine) {
      listed.add(mine);
      return { ...rowLine("unused", mine, i), units: r.units };
    }
    if (!r.grade && going.includes(r.code)) {
      listed.add(r.code);
      return { ...inProgress("unused", r.code), units: r.units };
    }
    return { key: `unused:${r.code}:${i}`, code: r.code, units: r.units, when: termLabel(r.term), grade: r.grade };
  });
  const other = [
    ...rows.filter((r) => !shown.has(r.code) && !listed.has(r)).map((r, i) => rowLine("other", r, i)),
    ...going.filter((c) => !shown.has(c) && !listed.has(c)).map((c) => inProgress("other", c)),
  ];
  const list = (name: string, lines: Line[]) =>
    !!lines.length && (
      <details className="rq-section rq-list" onToggle={(e) => !e.currentTarget.open && close()}>
        <summary>
          <span className="rq-chevron" aria-hidden="true" />
          <span className="rq-name">{name}</span>
          <span className="rq-count">{lines.length}</span>
        </summary>
        <div className="rq-body">{lines.map(line)}</div>
      </details>
    );

  return (
    <div className="rq">
      <div className="rq-head">
        <h2>Requirements</h2>
        <ul className="rq-key" aria-label="Status key">
          {MARKS.map((m) => (
            <li key={m}>
              <span aria-hidden="true">
                <StatusMark mark={m} />
              </span>
              {WORD[m]}
            </li>
          ))}
        </ul>
      </div>
      {!!excluded && <p className="rq-count-note">{excluded} {excluded === 1 ? "requirement" : "requirements"} left out of these totals. Confirm with an advisor.</p>}
      {SECTIONS.map(([name, test]) => {
        const groups = audit.groups.filter(test);
        if (!groups.length) return null;
        const n = countSection(groups, warned);
        const projected = withPlan?.groups.filter(test);
        const p = projected && countSection(projected, warned);
        const planned = groups.filter((g) => {
          if (g.waived_by === NOT_ON_DPR || markOf(g, warned.has(g.id)) !== "incomplete") return false;
          const status = projected?.find((x) => x.id === g.id)?.status;
          return status === "satisfied" || status === "waived";
        }).length;
        const needed = n.total - n.done - n.progress - planned;
        return (
          <details className="rq-section" key={name} onToggle={(e) => !e.currentTarget.open && close()}>
            <summary>
              <span className="rq-chevron" aria-hidden="true" />
              <span aria-hidden="true">
                <StatusMark mark={n.total > 0 && n.done === n.total ? "complete" : p && p.total > 0 && p.done === p.total ? "planned" : needed === 0 && n.progress > 0 ? "progress" : "incomplete"} />
              </span>
              <span className="rq-name">{name}</span>
              <span className="rq-flag" aria-hidden="true">
                {!!n.warned && <StatusMark mark="warning" />}
              </span>
              <span className="rq-status">
                <span><b>{n.done}/{n.total}</b> complete</span>
                {!!n.progress && <span>{n.progress} in progress</span>}
                {!!planned && <span>{planned} planned</span>}
                {p && p.total > 0 && p.done === p.total ? <strong>All covered by your plan</strong> : needed > 0 && <span>{needed} still needed</span>}
              </span>
              <span className="sr-only">
                {!!n.warned && `, ${n.warned} ${n.warned === 1 ? "warning" : "warnings"}`}
              </span>
            </summary>
            <div className="rq-body">{groups.map(requirement)}</div>
          </details>
        );
      })}
      {list(imported ? "Other courses on your record" : "Courses not used for a requirement", other)}
      {list("Courses not used for a requirement", notUsed)}
      <div className="rq-actions">
        <div className="rq-add">
          <button type="button" className="rq-link" aria-expanded={editing === "add"} disabled={locked} onClick={() => toggle("add")}>
            + Add a course{imported ? " your DPR doesn’t show" : ""}
          </button>
          {editing === "add" && (
            <FloatingCard label="Add a course" onClose={close}>
              <AddCourse profile={profile} edit={edit} locked={locked} />
            </FloatingCard>
          )}
        </div>
        {leave && <Button onClick={leave.go}>{leave.label}</Button>}
      </div>
    </div>
  );
}

/** "Does this look right?": the DPR-style summary, then the requirements, before the goals. */
export function ReviewScreen({
  profile,
  imported,
  edit,
  next,
  back,
}: {
  profile: Profile;
  imported: ImportResult | null;
  edit: (profile: Profile) => void;
  next: () => void;
  back: () => void;
}) {
  const audit = useLoad(() => getAudit(profile), [profile]);
  const programs = useLoad(getPrograms, []);
  const a = audit.data;
  const t = a?.totals;
  const gpa = profile.gpa;
  const sfGpa = profile.sf_state_gpa ?? t?.gpa_sf_state?.value;
  return (
    <main className="flow-page rq-page">
      <Stepper current={1} />
      <div className="flow-heading">
        <h1>Does this look right?</h1>
        <p>
          {imported ? "This is how GatorPath reads your DPR." : "This is what you told us, checked against the Bulletin."}{" "}
          Open a section to check its courses and grades.{imported && " Your DPR is the official record."}
        </p>
      </div>
      {audit.error ? (
        <ErrorCard text={audit.error} retry={audit.retry} />
      ) : !a || !t ? (
        <Loading label="Checking your record against the Bulletin…" />
      ) : (
        <>
          <section className="rq-summary" aria-label="Summary">
            <div className="rq-summary-head">
              <b>{programs.data?.find((p) => p.id === profile.program)?.title ?? profile.program}</b>
              <span>Catalog year {profile.catalog_year ?? a.catalog_year}</span>
            </div>
            <dl>
              {(
                [
                  ["Units", t.units, t.units_in_progress],
                  ["Upper-division units", t.upper_division_units, t.upper_division_units_in_progress ?? 0],
                ] as const
              ).map(([label, total, more]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>
                    {total.value + more}
                    {total.needed != null && <span> of {total.needed}</span>}
                  </dd>
                  {!!more && <dd className="rq-going">incl. {more} in progress</dd>}
                </div>
              ))}
              {gpa != null && (
                <div>
                  <dt>Overall GPA</dt>
                  <dd>{gpa.toFixed(3)}</dd>
                </div>
              )}
              {sfGpa != null && (
                <div>
                  <dt>SF State GPA</dt>
                  <dd>{sfGpa.toFixed(3)}</dd>
                </div>
              )}
            </dl>
          </section>
          <RequirementsView
            profile={profile}
            imported={imported}
            audit={a}
            edit={edit}
          />
          <div className="flow-action">
            <Button kind="ghost" onClick={back}><Icon name="back" size={16} /> Back</Button>
            <Button onClick={next}>Next <Icon name="arrow" size={16} /></Button>
          </div>
        </>
      )}
    </main>
  );
}
