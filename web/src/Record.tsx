import { useRef, useState } from "react";
import {
  EngineError,
  getCourse,
  getPrograms,
  importDpr,
  message,
  type Choice,
  type CourseInfo,
  type ImportResult,
  type Profile,
  type Taken,
} from "./api";
import { termLabel } from "./logic";
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
          <div className="howto-video" role="img" aria-label="Video coming soon">
            <i aria-hidden="true" />
            <span>Video coming soon</span>
          </div>
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
      <h2>Add your courses</h2>
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
      <Button onClick={() => done({ program, start_term: start })}>
        Continue <Icon name="arrow" />
      </Button>
    </div>
  );
}

export function RecordScreen({ done }: { done: (profile: Profile, imported?: ImportResult) => void }) {
  const [method, setMethod] = useState<"upload" | "type" | "new">("upload");
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
      {method === "type" && <TypedPanel done={done} />}
      {method === "new" && <NewStudentPanel done={done} />}
    </main>
  );
}


/** The record beside Review: add a course the DPR doesn't show, change a grade, finish or remove a course. */
export function RecordEditor({
  profile,
  titles,
  edit,
}: {
  profile: Profile;
  titles: Record<string, CourseInfo>;
  edit: (profile: Profile) => void;
}) {
  const rows = profile.completed ?? [];
  const going = profile.in_progress ?? [];
  const now = nearbyTerms(1, 0)[0];
  const [code, setCode] = useState("");
  const [grade, setGrade] = useState("A");
  const [term, setTerm] = useState(now);
  const [state, setState] = useState<{ loading?: boolean; error?: string }>({});
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
      setState({});
    } catch (e) {
      setState({ error: message(e) });
    }
  };
  return (
    <>
      <section className="section-card form-panel record-add">
        <h2>Fix your record</h2>
        <p>A course your DPR doesn’t show, or one you’ve finished since? Add it here.</p>
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
        <Button kind="secondary" icon="plus" onClick={add} disabled={!code || state.loading}>
          {state.loading ? "Finding it in the Bulletin…" : "Add course"}
        </Button>
        {state.error && <ErrorCard text={state.error} />}
      </section>
      <details className="section-card record-list">
        <summary>
          <span>Completed courses</span>
          <span>
            {rows.length} <Icon name="chevron" />
          </span>
        </summary>
        {rows.map((r, i) => (
          <div className="record-row" key={`${r.code}-${r.term ?? i}`}>
            <div>
              <b>
                {r.code} {r.transfer && <em className="transfer">Transfer</em>}
              </b>
              <small>{[titles[r.code]?.title, termLabel(r.term)].filter(Boolean).join(" · ")}</small>
            </div>
            <select
              aria-label={`Grade for ${r.code}`}
              value={r.grade}
              onChange={(e) => edit({ ...profile, completed: rows.map((x) => (x === r ? { ...x, grade: e.target.value } : x)) })}
            >
              {[...new Set([r.grade, ...GRADES])].map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>
            <button aria-label={`Remove ${r.code}`} onClick={() => edit({ ...profile, completed: rows.filter((x) => x !== r) })}>
              <Icon name="x" size={14} />
            </button>
          </div>
        ))}
      </details>
      <details className="section-card record-list">
        <summary>
          <span>In progress</span>
          <span>
            {going.length} <Icon name="chevron" />
          </span>
        </summary>
        {going.map((c) => (
          <div className="record-row" key={c}>
            <div>
              <b>{c}</b>
              <small>{titles[c]?.title}</small>
            </div>
            <select
              aria-label={`${c}: in progress, or the grade you got`}
              value=""
              onChange={(e) =>
                edit({
                  ...profile,
                  in_progress: going.filter((x) => x !== c),
                  completed: [...rows, { code: c, grade: e.target.value, term: now }],
                })
              }
            >
              <option value="">In progress</option>
              {GRADES.map((g) => (
                <option value={g} key={g}>
                  Finished: {g}
                </option>
              ))}
            </select>
            <button aria-label={`Remove ${c}`} onClick={() => edit({ ...profile, in_progress: going.filter((x) => x !== c) })}>
              <Icon name="x" size={14} />
            </button>
          </div>
        ))}
      </details>
    </>
  );
}
