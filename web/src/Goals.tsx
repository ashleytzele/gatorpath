import { useEffect, useState, type ReactNode } from "react";
import { getPathways, getPrograms, type Options, type Profile } from "./api";
import { goalText, pathwayLine, termLabel } from "./logic";
import { Button, DEMO, Icon, NAVIGATOR, Stepper, Tooltip, calmScroll, nearbyTerms, useLoad } from "./ui";

export type Picks = { interests: string[]; after: string[] };

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
const AFTER = ["Start working", "Graduate school"];
const NOT_SURE = "Not sure yet";
const PREVIEW_MAJORS = ["bs-cs", "ba-psychology", "ba-history", "bs-environmental-studies"];
const GOALS_KEY = "gatorpath-goals-v1";
function goalDraft(): { program?: string; options?: Options; picks?: Picks } {
  try { return JSON.parse(sessionStorage.getItem(GOALS_KEY) || "{}") || {}; } catch { return {}; }
}

/** Chips for the listed choices, "Not sure yet" (clears the others), and a box whose entries become removable chips. */
function ChipPicker({ names, picked, set }: { names: string[]; picked: string[]; set: (v: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const typed = picked.filter((p) => p !== NOT_SURE && !names.includes(p));
  const toggle = (name: string) =>
    set(
      name === NOT_SURE
        ? picked.includes(name) ? [] : [NOT_SURE]
        : [...picked.filter((p) => p !== NOT_SURE && p !== name), ...(picked.includes(name) ? [] : [name])],
    );
  const add = () => {
    const value = draft.trim();
    if (value) set([...picked.filter((p) => p !== NOT_SURE && p !== value), value]);
    setDraft("");
  };
  return (
    <>
      <div className="q-chips">
        {[...names, NOT_SURE].map((name) => (
          <button type="button" key={name} aria-pressed={picked.includes(name)} onClick={() => toggle(name)}>
            {picked.includes(name) && <Icon name="check" size={14} />}
            {name}
          </button>
        ))}
        {typed.map((name) => (
          <button type="button" className="typed" key={name} aria-label={`Remove ${name}`} onClick={() => toggle(name)}>
            {name} <Icon name="x" size={14} />
          </button>
        ))}
      </div>
      <div className="q-add">
        <input
          aria-label="Something else?"
          placeholder="Something else? Type it and press Enter"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <button type="button" className="button secondary" onClick={add}>
          Add
        </button>
      </div>
    </>
  );
}

function Q({ n, title, hint, group, id, children }: { n: number; title: ReactNode; hint?: string; group?: boolean; id?: string; children: ReactNode }) {
  const head = (
    <>
      <span className="q-num">{n}</span>
      <span className="q-text">
        <h2>{title}</h2>
        {hint && <small>{hint}</small>}
      </span>
    </>
  );
  return group ? (
    <fieldset className="q" id={id}>
      <legend className="q-head">{head}</legend>
      {children}
    </fieldset>
  ) : (
    <section className="q" id={id}>
      <div className="q-head">{head}</div>
      {children}
    </section>
  );
}

function Radio({ name, value, checked, set, children }: { name: string; value: string; checked: boolean; set: (v: string) => void; children: ReactNode }) {
  return (
    <label className="q-radio">
      <input type="radio" name={name} value={value} checked={checked} onChange={() => set(value)} />
      <span>{children}</span>
    </label>
  );
}

/** Math placement: the QR pathways of this major's roadmap, each with the line it leads to. Nothing if there are none. */
function QrQuestion({ n, program, qr, set }: { n: number; program: string; qr?: string; set: (v: string) => void }) {
  const found = useLoad(() => getPathways(program), [program]);
  if (!found.data?.length) return null;
  return (
    <Q n={n} group title="What is your math placement?" hint="We use it to place your first math class.">
      {found.data.map((p) => (
        <Radio name="qr" key={p.pathway} value={p.pathway} checked={qr === p.pathway} set={set}>
          <b>QR {p.pathway}</b>
          <small>{pathwayLine(p.courses)}</small>
        </Radio>
      ))}
      <a className="q-link" href="https://gatorsmartstart.sfsu.edu/pathways" target="_blank" rel="noreferrer">
        Not sure? Find your Pathway/Category on Gator Smart Start <Icon name="arrow" size={14} />
      </a>
    </Q>
  );
}

export function GoalsScreen({
  profile,
  saved,
  picks,
  needs,
  build,
  back,
}: {
  profile: Profile;
  saved: Options;
  picks: Picks;
  needs?: string;
  build: (options: Options, picks: Picks) => void;
  back: () => void;
}) {
  const [draft] = useState(() => {
    const found = goalDraft();
    return found.program === profile.program ? found : {};
  });
  const previous = draft.options ?? {};
  // the draft is written on every change, so it is newer than the options the last build kept
  const from = <K extends keyof Options>(key: K) => (key in previous ? previous[key] : saved[key]);
  const [interests, setInterests] = useState(draft.picks?.interests ?? picks.interests);
  const [after, setAfter] = useState(draft.picks?.after ?? picks.after);
  const [previewMajor, setPreviewMajor] = useState(profile.program);
  const [graduateBy, setGraduateBy] = useState(from("graduate_by") ?? "");
  const [units, setUnits] = useState(String(from("max_units_per_term") ?? ""));
  const [summer, setSummer] = useState(from("include_summer") ?? false);
  const [winter, setWinter] = useState(from("include_winter") ?? false);
  const [f1, setF1] = useState(String((previous as { f1_choice?: string }).f1_choice ?? (from("f1") === true ? "yes" : from("f1") === false ? "no" : "")));
  const [f1Missing, setF1Missing] = useState(false); // Build was pressed without an answer
  const [qr, setQr] = useState(from("qr_pathway") ?? profile.qr_pathway);
  const [start, setStart] = useState(from("start_term") ?? "");
  useEffect(() => {
    try { sessionStorage.setItem(GOALS_KEY, JSON.stringify({
      program: profile.program,
      picks: { interests, after },
      options: { graduate_by: graduateBy, max_units_per_term: units ? Number(units) : null, // null, not left out: "back to the default" must win over an older value
        include_summer: summer, include_winter: winter, f1: f1 === "yes" ? true : f1 === "no" ? false : null, f1_choice: f1,
        qr_pathway: qr, start_term: start },
    })); } catch { /* storage unavailable */ }
  }, [interests, after, graduateBy, units, summer, winter, f1, qr, start]);
  const major = DEMO ? previewMajor : profile.program;
  const goals = major === "bs-environmental-studies" ? null : (GOALS[major] ?? []);
  const brandNew = !profile.completed?.length && !profile.in_progress?.length;
  const askQr = !profile.qr_pathway && (brandNew || needs === "qr_pathway");
  const programs = useLoad(getPrograms, []);
  const title = programs.data?.find((p) => p.id === major)?.title ?? major;
  let n = 0;
  const goal = goalText(interests, after);
  return (
    <main className="flow-page goals-page">
      <Stepper current={2} />
      <div className="flow-heading">
        <h1>What matters to you?</h1>
        <p>Your answers set your pace and shape the courses we pick. You can change them later, or in the chat.</p>
      </div>
      {needs && (
        <div className="error-card" role="alert">
          <Icon name="warning" />
          <div>
            <b>
              {needs === "qr_pathway"
                ? "We need your math placement to place your first math class."
                : "We need to know when your plan starts."}
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
              setInterests([]);
            }}
            aria-label="Preview goal options for major"
          >
            {[...new Set([profile.program, ...PREVIEW_MAJORS])].map((id) => (
              <option key={id}>{id}</option>
            ))}
          </select>
        )}
      </div>
      {goals ? (
        <Q n={++n} title="What are you interested in?" hint="Pick any that fit. We’ll choose your electives around them.">
          <ChipPicker names={goals} picked={interests} set={setInterests} />
        </Q>
      ) : (
        <div className="no-goals-note">
          <Icon name="check" />
          <div>
            <b>No focus question needed for {title}</b>
            <span>This major has no elective choices, so we’ll skip this step.</span>
          </div>
        </div>
      )}
      <Q n={++n} title="What do you want to do after you graduate?" hint="This helps us pick courses that lead there.">
        <ChipPicker names={AFTER} picked={after} set={setAfter} />
      </Q>
      <Q n={++n} title="When do you want to graduate?" hint="We’ll tell you if that pace looks realistic.">
        <select aria-label="When do you want to graduate?" value={graduateBy} onChange={(e) => setGraduateBy(e.target.value)}>
          <option value="">Follow the recommended pace</option>
          {nearbyTerms(0, 12).map((t) => (
            <option value={t} key={t}>
              {termLabel(t)}
            </option>
          ))}
        </select>
      </Q>
      <Q n={++n} group title="How many units can you take each term?" hint="Think about work and family. Fewer units means more terms.">
        <Radio name="units" value="12" checked={units === "12"} set={setUnits}>12 units</Radio>
        <Radio name="units" value="" checked={units === ""} set={setUnits}>About 15 units (recommended)</Radio>
        <Radio name="units" value="18" checked={units === "18"} set={setUnits}>18 units</Radio>
        {!["", "12", "18"].includes(units) && <Radio name="units" value={units} checked set={setUnits}>{units} units (set earlier)</Radio>}
        <p className="q-note">More than the roadmap’s load needs an advisor’s OK.</p>
      </Q>
      <Q n={++n} group title="Will you take summer or Winter Session classes?" hint="They can help you finish sooner. Leave both off if not.">
        <label className="q-radio">
          <input type="checkbox" checked={summer} onChange={(e) => setSummer(e.target.checked)} />
          <span>Summer</span>
        </label>
        <label className="q-radio">
          <input type="checkbox" checked={winter} onChange={(e) => setWinter(e.target.checked)} />
          <span>Winter Session (January)</span>
        </label>
      </Q>
      <Q
        n={++n}
        group
        id="q-f1"
        title={<>Are you on an F-1 student visa? <Tooltip text="F-1 students need at least 12 units every fall and spring." /></>}
        hint="This sets your minimum load. Please answer, so we don't plan terms under 12 units for you by mistake."
      >
        <Radio name="f1" value="no" checked={f1 === "no"} set={(v) => { setF1(v); setF1Missing(false); }}>No</Radio>
        <Radio name="f1" value="yes" checked={f1 === "yes"} set={(v) => { setF1(v); setF1Missing(false); }}>Yes</Radio>
        <Radio name="f1" value="skip" checked={f1 === "skip"} set={(v) => { setF1(v); setF1Missing(false); }}>Prefer not to say</Radio>
        {f1Missing && <p className="q-error" role="alert">Choose Yes, No or Prefer not to say, then build your plan.</p>}
        {f1 === "yes" && (
          <p className="q-note">Every fall and spring stays at 12 units or more. For other visa questions, ask the international office.</p>
        )}
      </Q>
      {askQr && <QrQuestion n={++n} program={profile.program} qr={qr} set={setQr} />}
      {needs === "start_term" && (
        <Q n={++n} title="When does your plan start?" hint="Your plan starts here.">
          <select aria-label="When does your plan start?" value={start} onChange={(e) => setStart(e.target.value)}>
            <option value="">Choose a term</option>
            {nearbyTerms(0, 4).map((t) => (
              <option value={t} key={t}>
                {termLabel(t)}
              </option>
            ))}
          </select>
        </Q>
      )}
      <div className="flow-action">
        <Button kind="ghost" onClick={back}><Icon name="back" size={16} /> Back</Button>
        <Button
          onClick={() => {
            if (!f1) {
              setF1Missing(true);
              return calmScroll(document.getElementById("q-f1"), "center");
            }
            build(
              {
                ...(goal && { goal }),
                ...(graduateBy && { graduate_by: graduateBy }),
                ...(f1 && { f1: f1 === "yes" ? true : f1 === "no" ? false : undefined }),
                ...(qr && { qr_pathway: qr }),
                ...(start && { start_term: start }),
                ...(summer && { include_summer: true }),
                ...(winter && { include_winter: true }),
                ...(units && { max_units_per_term: Number(units) }),
              },
              { interests, after },
            );
          }}
        >
          Build my plan <Icon name="arrow" />
        </Button>
      </div>
    </main>
  );
}
