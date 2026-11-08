import { useEffect, useLayoutEffect, useRef, useState } from "react";
import BuildingScreen from "./Building";
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
import { GoalsScreen, type Picks } from "./Goals";
import { Landing } from "./Landing";
import { RecordScreen, RequirementsView, ReviewScreen } from "./Record";
import { FloatingCard } from "./FloatingCard";
import { StatusMark } from "./StatusMark";
import { ChatPanel } from "./Chat";
import { changeLine, countSection, splitWhy, suggestions, termLabel, unitText, warnedGroups, withPlanned, type ChatLine } from "./logic";
import {
  ASK_ADVISOR, Button, DEMO, ErrorCard, Footer, Header, Icon, Loading, Logo, NAVIGATOR,
  Stepper, StatusBadge, plainText, useLoad, type Screen,
} from "./ui";

/** "record" is Your record with the plan beside it, reached from the Plan tab, not the tab bar. */
type Tab = "plan" | "electives" | "schedule" | "record";

const isDone = (g: Group) => g.status === "satisfied" || g.status === "waived";

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
const isSlot = (c: string | Slot): c is Slot => typeof c !== "string";
const yearOf = (term: string) => {
  const year = Number(term.slice(0, 4));
  const first = term.endsWith("fall") ? year : year - 1;
  return `${first}–${String(first + 1).slice(2)}`;
};
const unitsOf = (c: string | Slot, info: Record<string, CourseInfo>) =>
  isSlot(c) ? c.units : parseFloat(String(info[c]?.units)) || 0;
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
  whatIf: (change: Options) => void;
  aiDown: boolean;
  sections: Record<string, string[]>; // {term: class numbers} the student chose
  setSections: (term: string, keep: string[]) => void;
  aiBusy: boolean; // the chat's answer replaces the plan, so a section chosen meanwhile would be lost
  ask: (text: string) => void; // sends a message to the chat, as if the student typed it
};

function Tabs({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  const items: [Tab, string][] = [
    ["plan", "Plan"],
    ["electives", "Electives & GE"],
    ["schedule", "Schedule"],
  ];
  const current = tab === "record" ? "plan" : tab; // the requirements are the plan's
  return (
    <nav className="app-tabs" aria-label="Your plan">
      {items.map(([key, label]) => (
        <button
          type="button"
          key={key}
          className={current === key ? "active" : ""}
          aria-current={current === key ? "page" : undefined}
          onClick={() => setTab(key)}
        >
          {label}
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

const sentence = (s: string) => (/[.!?]$/.test(s) ? s : `${s}.`);
const listed = (xs: string[]) => (xs.length > 1 ? `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}` : xs[0]);

/** One office `see_advisor` names: this student's reasons, its links (booking, page, email), then where and how. */
function AdvisorRow({ a, audit }: { a: Advisor; audit: Audit }) {
  const book = a.how_to_book?.match(/https?:\/\/\S+/)?.[0].replace(/[.,;)]+$/, "");
  const how = a.how_to_book?.split(/(?<=\.)\s+/).filter((s) => !/https?:\/\//.test(s)).join(" ");
  const emails = a.contact?.match(/[\w.+-]+@[\w-]+(\.[\w-]+)+/g) ?? [];
  const rest = emails.reduce((text, e) => text.replace(e, ""), a.contact ?? "").replace(/^[\s,]+|[\s,]+$/g, "");
  const page = a.link?.startsWith("http") ? a.link : undefined; // the DPR's "link" is where to find it, not a URL
  const where = [a.location, rest, !page && a.link].filter(Boolean).join(" · ");
  const links = [
    ...(book ? [{ href: book, text: book === NAVIGATOR ? "Book in Navigator" : "How to book" }] : []),
    ...(page && page !== book ? [{ href: page, text: page.replace(/^https?:\/\//, "").replace(/\/$/, "") }] : []),
    ...emails.map((e) => ({ href: `mailto:${e}`, text: e })),
  ];
  return (
    <div className="pl-advisor">
      <b>{a.who}</b>
      <p>{plainText(a.why.map(sentence).join(" "), audit)}</p>
      {!!links.length && (
        <p className="pl-links">
          {links.map((l) => (
            <a href={l.href} target="_blank" rel="noreferrer" key={l.href}>
              {l.text}
            </a>
          ))}
        </p>
      )}
      {where && <p className="pl-where">{where}</p>}
      {how && <p className="pl-where">{how}</p>}
    </div>
  );
}

/** A course's facts from the Bulletin, and why it sits in its term. */
function CourseFacts({ code, why, going }: { code: string; why?: string; going?: boolean }) {
  const course = useLoad(() => getCourse(code), [code]);
  const c = course.data;
  const [more, setMore] = useState(false);
  const [long, setLong] = useState(false); // the description runs past its two lines
  const text = useRef<HTMLParagraphElement>(null);
  useLayoutEffect(() => {
    if (text.current && !more) setLong(text.current.scrollHeight > text.current.clientHeight + 1);
  }, [c, more]);
  if (course.error) return <ErrorCard text={course.error} retry={course.retry} />;
  if (!c) return <p role="status">Finding it in the Bulletin…</p>;
  const { now, opens } = splitWhy(why);
  const seasons = (["fall", "spring", "summer"] as const)
    .filter((s) => c.offered_terms?.[s]?.[0])
    .map((s) => s[0].toUpperCase() + s.slice(1));
  return (
    <>
      {c.description && (
        <p ref={text} className={`pl-desc ${more ? "" : "clamped"}`}>
          {c.description}
        </p>
      )}
      {(long || more) && (
        <button type="button" className="pl-link" aria-expanded={more} onClick={() => setMore(!more)}>
          {more ? "Less" : "More"}
        </button>
      )}
      <dl className="pl-facts">
        <dt>Needs</dt>
        <dd>{c.prereq?.raw_text || "None listed in the Bulletin"}</dd>
        <dt>Offered</dt>
        <dd>{seasons.length ? listed(seasons) : "No offering history here: check Class Search"}</dd>
        {(going || now) && (
          <>
            <dt>Why now</dt>
            <dd>{going ? "You’re taking it now." : plainText(now)}</dd>
          </>
        )}
        {opens && (
          <>
            <dt>Opens</dt>
            <dd>{opens}</dd>
          </>
        )}
      </dl>
    </>
  );
}

/** Courses that fit an open choice (or replace a chosen one) in its term, to Select. */
function ChoiceOptions({ work, target, select }: { work: Work; target: Target; select: (code: string, option: Option) => void }) {
  const found = useLoad(
    () => getElectives(work.student, target.group, { semesters: work.semesters }, target.term),
    [target.group, target.term, target.replacing],
  );
  // ponytail: the first three that fit, in the server's order; the Electives & GE tab lists the rest
  const options = (found.data?.options ?? [])
    .filter((o) => o.readiness !== "blocked" && o.code !== target.replacing)
    .slice(0, 3);
  const term = termLabel(target.term);
  return (
    <>
      <p className="pl-card-lead">
        Select one for {term}
        {target.replacing ? `, in place of ${target.replacing}` : ""}.
      </p>
      {found.loading && !found.data && <p role="status">Finding courses that fit…</p>}
      {found.error && <ErrorCard text={found.error} retry={found.retry} />}
      {found.data?.approval && (
        <p>
          {found.data.approval}. {ASK_ADVISOR} which courses count.
        </p>
      )}
      {!!options.length && (
        <ul className="pl-options">
          {options.map((o) => (
            <li key={o.code}>
              <b>{o.code}</b>
              <span>
                {o.title}
                {o.readiness === "check" && (
                  <small> · Check: {plainText(o.cannot_check?.join("; ") || o.note || "its prerequisites", work.audit)}</small>
                )}
              </span>
              <button type="button" className="pl-link" disabled={work.aiBusy} onClick={() => select(o.code, o)}>
                Select<span className="sr-only"> {o.code}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {found.data && !options.length && !found.data.approval && <p>No course that fits {term} was found.</p>}
      {!work.aiDown && (
        <p className="pl-card-lead">
          Or{" "}
          <button
            type="button"
            className="pl-link"
            disabled={work.aiBusy}
            onClick={() =>
              work.ask(
                target.replacing
                  ? `Swap ${target.replacing} in ${term} for another course for ${target.title}`
                  : `Choose a course for ${target.title} in ${term}`,
              )
            }
          >
            ask the chat to choose one
          </button>
        </p>
      )}
    </>
  );
}

/** The floating card of a row: a course's facts, or an open choice's options. */
function CourseCard({
  work,
  item,
  term,
  why,
  going,
  select,
}: {
  work: Work;
  item: string | Slot;
  term?: string;
  why?: string;
  going?: boolean;
  select: (target: Target, code: string, option: Option) => void;
}) {
  const [swapping, setSwapping] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (swapping) heading.current?.focus(); // the Swap button is gone: keep focus in the card
  }, [swapping]);
  if (isSlot(item)) {
    const target = { group: item.slot, term: term!, title: slotLabel(item, work.audit) }; // slots are only in planned terms
    return (
      <div className="pl-card">
        <h3>{target.title}</h3>
        <p className="pl-card-sub">
          {item.units ? `Open choice · ${unitText(item.units)}` : "A course you choose for another requirement can cover this"}
        </p>
        <ChoiceOptions work={work} target={target} select={(code, option) => select(target, code, option)} />
      </div>
    );
  }
  const about = work.info[item] ?? work.audit.courses[item];
  const pick = work.picks.find((p) => p.code === item);
  const swap = pick && {
    group: pick.group,
    term: pick.term,
    title: slotLabel({ slot: pick.group, units: 0 }, work.audit),
    replacing: item,
  };
  return (
    <div className="pl-card">
      <h3 tabIndex={-1} ref={heading}>
        {item}
      </h3>
      <p className="pl-card-sub">{[about?.title, about && unitText(about.units)].filter(Boolean).join(" · ")}</p>
      {swap && swapping ? (
        <ChoiceOptions work={work} target={swap} select={(code, option) => select(swap, code, option)} />
      ) : (
        <>
          <CourseFacts code={item} why={why} going={going} />
          <p className="pl-card-actions">
            {about && <span>Bulletin p.{about.source_page}</span>}
            {!work.aiDown && (
              <button type="button" className="pl-link" disabled={work.aiBusy} onClick={() => work.ask(`Tell me about ${item} in my plan`)}>
                Ask about this course
              </button>
            )}
            {swap && (
              <button type="button" className="pl-link" disabled={work.aiBusy} onClick={() => setSwapping(true)}>
                Swap it
              </button>
            )}
          </p>
        </>
      )}
    </div>
  );
}

/** One stop on the route: a term and its courses ("This term" holds what's in progress now). */
type Stop = { key: string; title: string; term?: string; courses: (string | Slot)[]; why?: Record<string, string>; now?: boolean };

function PlanView({
  work,
  coverage,
  select,
  openSchedule,
  openRecord,
}: {
  work: Work;
  coverage?: { done: number; total: number };
  select: (target: Target, code: string, option: Option) => void;
  openSchedule: () => void;
  openRecord: () => void;
}) {
  const { audit, check, info, plan, semesters, student } = work;
  const pace = plan.pace;
  const [preview, setPreview] = useState<"" | "problem" | "unreachable">("");
  const [open, setOpen] = useState(""); // the row whose card is open: one at a time
  useEffect(() => setOpen(""), [semesters]); // a change moves rows under an open card
  const choices = semesters.reduce((n, s) => n + s.courses.filter(isSlot).length, 0);
  const graduation = semesters[semesters.length - 1]?.term; // the plan as it stands: a chat or a pick can move it past build_plan's estimate
  const unreachable = pace?.on_time === false && !!pace.why_not?.length;
  const planState = preview || (!check.valid ? "problem" : unreachable ? "unreachable" : "");
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
  const going = student.in_progress ?? [];
  const stops: Stop[] = [
    ...(going.length ? [{ key: "now", title: "This term", courses: going, now: true }] : []),
    ...semesters.map((s) => ({ key: s.term, title: termLabel(s.term), term: s.term, courses: s.courses, why: s.why })),
  ];
  const about = (code: string) => info[code] ?? audit.courses[code];
  const units = (c: string | Slot) => (isSlot(c) ? c.units : parseFloat(String(about(c)?.units)) || 0);
  const count = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  return (
    <div className="app-content plan-tab">
      {DEMO && (
        <div className="variant-switcher">
          <span>Preview plan state</span>
          {[
            ["", "As it is"],
            ["problem", "Has a problem"],
            ["unreachable", "Date unreachable"],
          ].map(([value, label]) => (
            <button
              className={preview === value ? "active" : ""}
              onClick={() => setPreview(value as typeof preview)}
              key={value}
            >
              {label}
            </button>
          ))}
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
            <Button kind="secondary" disabled={work.aiBusy} onClick={() => work.whatIf({ include_summer: true })}>
              Add summer terms
            </Button>
            <a className="button secondary" href={NAVIGATOR} target="_blank" rel="noreferrer">
              {ASK_ADVISOR}
            </a>
          </div>
        </div>
      )}
      <section className="pl-head">
        <h1>
          You {planState === "problem" ? "could" : "can"} graduate <em>{termLabel(graduation)}</em>
        </h1>
        {planState === "problem" && (
          <p className="hero-note">Once the problems above are fixed. Until then the date isn’t certain.</p>
        )}
        <p className="pl-sub">
          {count(semesters.length, "semester")} after this one ·{" "}
          {choices ? `${count(choices, "choice")} still open` : "all choices made"}
        </p>
        {pace && (
          <p>
            {pace.min_terms_by_prereqs >= pace.min_terms_by_units && chain.length
              ? `Your longest prerequisite chain, ${chain.join(" → ")}, sets this date.`
              : `Your units per term set this date: you need at least ${pace.min_terms_by_units} terms at this pace.`}
          </p>
        )}
        <p>
          {coverage && `With this plan, ${coverage.done} of ${coverage.total} requirements are complete. `}
          <button type="button" className="pl-link" onClick={openRecord}>
            See your requirements
          </button>
        </p>
      </section>
      <ol className="pl-route" aria-label="Route to graduation">
        {stops.map((stop, si) => {
          const next = !!stop.term && stop.term === semesters[0]?.term;
          const grad = !!stop.term && stop.term === graduation;
          const year = stop.term && yearOf(stop.term);
          const before = stops[si - 1]?.term;
          const kind = [stop.now && "now", next && "next", grad && "grad", /summer|winter/.test(stop.term ?? "") && "short"];
          return (
            <li className={`pl-stop ${kind.filter(Boolean).join(" ")}`} key={stop.key}>
              {year && (!before || yearOf(before) !== year) && (
                <p className="pl-year">
                  <span>{year}</span>
                </p>
              )}
              <div className="pl-term">
                <span className="pl-dot" aria-hidden="true">
                  {grad && <Icon name="flag" size={12} />}
                </span>
                <h2>{stop.title}</h2>
                <span>{unitText(stop.courses.reduce((t, c) => t + units(c), 0))}</span>
                {stop.now && <b className="pl-badge now">In progress</b>}
                {next && <b className="pl-badge">Register next</b>}
                {grad && <b className="pl-badge">Graduate</b>}
                {next && (
                  <button type="button" className="pl-link pl-schedule" onClick={openSchedule}>
                    See its schedule →
                  </button>
                )}
              </div>
              <ul className="pl-rows">
                {stop.courses.map((c, ci) => {
                  const key = `${stop.key}|${ci}`; // by place: a choice filled in place keeps its row, and focus
                  const slot = isSlot(c);
                  const title = slot ? slotLabel(c, audit) : about(c)?.title;
                  return (
                    <li key={key}>
                      <button
                        type="button"
                        className={`pl-row ${slot ? "open-choice" : ""}`}
                        data-code={slot ? undefined : c}
                        aria-expanded={open === key}
                        onClick={(e) => {
                          e.currentTarget.focus(); // Safari doesn't focus a clicked button; the card returns focus here
                          setOpen(open === key ? "" : key);
                        }}
                      >
                        {!slot && <b className="pl-code">{c}</b>}
                        <span className="pl-title">{title}</span>
                        <span className="pl-units">
                          {!!units(c) && (
                            <>
                              {units(c)}
                              <span className="sr-only"> units</span>
                            </>
                          )}
                        </span>
                        <span className="pl-tag">{slot ? "Not chosen yet" : countsFor(c, work.picks, audit)}</span>
                      </button>
                      {open === key && (
                        <FloatingCard label={slot ? `Choose a course for ${title}` : `${c} details`} onClose={() => setOpen("")}>
                          <CourseCard
                            work={work}
                            item={c}
                            term={stop.term}
                            why={slot ? undefined : stop.why?.[c]}
                            going={stop.now}
                            select={(target, code, option) => {
                              setOpen("");
                              select(target, code, option);
                            }}
                          />
                        </FloatingCard>
                      )}
                    </li>
                  );
                })}
              </ul>
            </li>
          );
        })}
      </ol>
      {!!warnings.length && (
        <details className="pl-checks">
          <summary>
            <StatusMark mark="warning" />
            <b>{count(warnings.length, "thing")} to check</b>
            <span className="rq-chevron" aria-hidden="true" />
          </summary>
          <ul>
            {warnings.map((w) => (
              <li key={w}>{plainText(w, audit)}</li>
            ))}
          </ul>
        </details>
      )}
      <section className="pl-section" aria-labelledby="pl-advisors">
        <h2 id="pl-advisors">Talk to an advisor</h2>
        <p className="pl-lead">Take this plan with you. Your DPR and your advisor have the final word.</p>
        {advisors.map((a) => (
          <AdvisorRow a={a} audit={audit} key={a.role} />
        ))}
        {audit.directory?.link && (
          <p className="pl-lead">
            Not sure who to ask?{" "}
            <a href={audit.directory.link} target="_blank" rel="noreferrer">
              The {audit.directory.who.replace(/ \(.*\)$/, "")}
            </a>{" "}
            lists every advising office.
          </p>
        )}
      </section>
      <div className="plan-actions">
        <Button kind="secondary" icon="download" onClick={() => window.print()}>
          Print my plan
        </Button>
      </div>
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
  locked,
}: {
  option: Option;
  chosen: boolean;
  audit: Audit;
  choose: () => void;
  locked: boolean; // the AI is working: a choice now would be lost
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
        <Button kind={chosen ? "secondary" : "primary"} disabled={blocked || chosen || locked} onClick={choose}>
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
      locked={work.aiBusy}
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

/** A plan after an AI answer: the API returns what it was sent of each term, so keep what only build_plan has (why). */
const applyAnswer = <T extends { semesters: Semester[]; plan: PlanResult; options: Partial<Profile>; info: Record<string, CourseInfo>; sections: Record<string, string[]> }>(
  state: T,
  r: Assisted,
) => ({
  ...state,
  semesters: r.semesters.map((s) => ({ ...state.semesters.find((o) => o.term === s.term), ...s })),
  check: r.check,
  picks: r.picks,
  plan: r.rebuilt ?? state.plan,
  options: { ...state.options, ...r.options },
  info: { ...state.info, ...r.rebuilt?.courses, ...r.check.courses },
  sections: r.sections ?? state.sections,
});

function AppWorkspace({
  profile,
  built,
  imported,
  notes,
}: {
  profile: Profile;
  built: Built;
  imported: ImportResult | null;
  notes: string[];
}) {
  const [tab, setTab] = useState<Tab>("plan");
  const [picker, setPicker] = useState<Target | null>(null);
  const [chat, setChat] = useState(false);
  const [docked, setDocked] = useState(true); // on a wide screen the chat sits beside the plan until hidden
  const lastTerm = (semesters: Semester[]) => semesters[semesters.length - 1]?.term ?? "";
  const down = (m: string) => /isn't connected/.test(m); // the AI has no key here
  const [lines, setLines] = useState<ChatLine[]>(() => [
    ...(built.filled ? [{ kind: "ai" as const, text: built.filled.reply }] : []),
    ...(built.filled?.changed
      ? [changeLine(built.plan.semesters, built.filled.semesters, built.filled.check, lastTerm(built.filled.semesters), true)]
      : []),
    ...(built.why ? [{ kind: "refused" as const, text: built.why }] : []),
  ]);
  const [left, setLeft] = useState(built.filled?.left);
  const [sending, setSending] = useState(false);
  const [aiDown, setAiDown] = useState(down(built.why));
  const [toast, setToast] = useState("");
  const [state, setState] = useState(() => {
    const first = {
    options: built.options as Partial<Profile>,
    plan: built.plan,
    semesters: built.plan.semesters,
    check: built.plan.check ?? ({ valid: true, errors: [] } as Checked),
    info: built.plan.courses ?? {},
    picks: [] as Pick[],
    sections: {} as Record<string, string[]>,
    };
    return built.filled ? applyAnswer(first, built.filled) : first;
  });
  const [busy, setBusy] = useState("");
  const [failed, setFailed] = useState("");
  const [previous, setPrevious] = useState<typeof state | null>(null);
  const student = { ...profile, ...state.options };
  const log = (line: ChatLine) => setLines((ls) => [...ls, line]);
  const say = (text: string) => log({ kind: "ai", text });
  const history = (ls: ChatLine[]): ChatMessage[] =>
    ls.filter((l) => l.kind === "me" || l.kind === "ai").map((l) => ({ role: l.kind === "me" ? "user" : "assistant", content: l.text }));
  /** The AI could not answer: a plain line, and what that means for the input. */
  const unanswered = (e: unknown) => {
    const m = message(e);
    if (down(m)) setAiDown(true);
    else if (/limit for everyone/.test(m)) setLeft({ hour: left?.hour ?? 0, day: 0 });
    else if (/times this hour/.test(m)) setLeft({ hour: 0, day: left?.day ?? 0 });
    log({ kind: "refused", text: m });
  };
  /** An AI answer: its words, then one line for any change (check_plan already passed it on the server). */
  const absorb = (r: Assisted) => {
    if (r.left) setLeft(r.left);
    say(r.reply);
    if (!r.changed) return;
    setPrevious(state);
    setState(applyAnswer(state, r));
    log(changeLine(state.semesters, r.semesters, r.check, lastTerm(r.semesters), true));
  };
  const showToast = (x: string) => {
    setToast(x);
    setTimeout(() => setToast(""), 2500);
  };
  /** A change GatorPath makes itself. Only a plan that passes the check is applied; otherwise nothing changes.
   * `applied`: a fact the student states (a record edit) stands either way, and a failed check shows its problem. */
  const attempt = async (label: string, run: () => Promise<typeof state>, note = "", applied = false) => {
    if (sending || busy) return;
    setBusy(label);
    setFailed("");
    try {
      const next = await run();
      const line = changeLine(state.semesters, next.semesters, next.check, lastTerm(next.semesters), applied);
      if (line.kind !== "refused") {
        setPrevious(state);
        setState(next);
        line.text += note;
      }
      log(line);
    } catch (e) {
      log({ kind: "refused", text: `Not changed · ${message(e)}` });
    } finally {
      setBusy("");
    }
  };
  const whatIf = (change: Options) =>
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
      state.picks.length ? " · your course choices were cleared" : "",
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
        const pace = { ...state.plan.pace!, fold_last_term: undefined }; // it is done: don't offer it again
        return { ...state, semesters, check, picks, plan: { ...state.plan, pace }, info: { ...state.info, ...check.courses } };
      },
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
    );
  };
  /** A record edit after the plan exists: re-checked as the plan stands, choices kept, logged with Undo. */
  const editRecord = (edited: Profile) =>
    attempt(
      "Checking your plan…",
      async () => {
        const options = { ...state.options, ...edited };
        const check = await checkPlan({ ...profile, ...options }, { semesters: state.semesters });
        return { ...state, options, check, info: { ...state.info, ...check.courses } };
      },
      "",
      true,
    );
  const fill = async () => {
    if (sending || busy) return;
    setBusy("Choosing your courses with AI…");
    setFailed("");
    try {
      const r = await assist(student, state.semesters, state.picks, [], state.sections, told.current ? [] : notes);
      told.current = true;
      absorb(r);
    } catch (e) {
      unanswered(e); // the plan works without AI
    } finally {
      setBusy("");
    }
  };
  const send = async (text: string) => {
    if (sending || busy) return;
    const asked: ChatLine[] = [...lines, { kind: "me", text }];
    setLines(asked);
    setSending(true);
    try {
      absorb(await assist(student, state.semesters, state.picks, history(asked), state.sections));
    } catch (e) {
      unanswered(e);
    } finally {
      setSending(false);
    }
  };
  const suggest = (id: string) => {
    const pace = state.plan.pace;
    if (id === "sooner") applyFold();
    else if (id === "lighter" && pace?.normal_load) whatIf({ max_units_per_term: pace.normal_load.max_units_per_term });
    else if (id === "summer") whatIf({ include_summer: true });
    else if (id === "winter") whatIf({ include_winter: true });
    else if (id === "choose") fill();
  };
  const show = (codes: string[]) => {
    setTab("plan");
    setChat(false); // on a phone the chat covers the page
    setTimeout(() => {
      const rows = codes.flatMap((c) => [...document.querySelectorAll<HTMLElement>(`[data-code="${CSS.escape(c)}"]`)]);
      rows.forEach((r) => {
        r.closest("details")?.setAttribute("open", "");
        r.classList.add("row-flash");
      });
      const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      rows[0]?.scrollIntoView({ block: "center", behavior: calm ? "auto" : "smooth" });
      setTimeout(() => rows.forEach((r) => r.classList.remove("row-flash")), 2500);
    }, 50);
  };
  const told = useRef(!!built.filled); // the DPR notes go with the first request only
  useEffect(() => {
    const open = () => {
      setChat(true);
      setDocked(true);
    };
    document.addEventListener("gator-ask", open);
    return () => document.removeEventListener("gator-ask", open);
  }, []);
  // the record as it stands (edits change it), and as if every planned course were passed: "With your plan"
  const record = useLoad(() => getAudit(student), [state.options]);
  const withPlan = useLoad(() => getAudit(withPlanned(student, state.semesters)), [state.options, state.semesters]);
  const audit = record.data ?? built.audit;
  const work: Work = {
    ...state,
    student,
    audit,
    busy,
    failed,
    whatIf,
    aiDown,
    aiBusy: sending || !!busy,
    ask: (text) => {
      if (sending || busy) return;
      setChat(true);
      setDocked(true);
      send(text);
    },
    setSections: (term, keep) => {
      if (sending || busy) return;
      setPrevious(state);
      log({ kind: "ok", text: `Class sections for ${termLabel(term)} updated` });
      setState({ ...state, sections: { ...state.sections, [term]: keep } });
    },
  };
  const undo = () => {
    if (!previous || sending || busy) return;
    setState(previous);
    setPrevious(null);
    say("I put your plan back the way it was.");
  };
  const go = (to: Tab) => {
    setTab(to);
    window.scrollTo(0, 0);
  };
  return (
    <div className={`workspace ${docked ? "" : "chat-hidden"}`}>
      <div className="workspace-main">
        <Tabs tab={tab} setTab={setTab} />
        {tab === "plan" && (
          <PlanView
            work={work}
            coverage={withPlan.data && countSection(withPlan.data.groups, warnedGroups(student, imported))}
            select={choose}
            openSchedule={() => setTab("schedule")}
            openRecord={() => go("record")}
          />
        )}
        {tab === "record" && (
          <div className="app-content">
            <div className="page-title">
              <h1>Your requirements</h1>
              <p>What your record covers now, and with your plan. An edit here re-checks your plan as it stands.</p>
            </div>
            <RequirementsView
              profile={student}
              imported={imported}
              audit={audit}
              withPlan={withPlan.data}
              semesters={state.semesters}
              edit={editRecord}
              leave={{ label: "Back to your plan", go: () => go("plan") }}
            />
          </div>
        )}
        {tab === "electives" && (
          <ElectivesView work={work} openPicker={setPicker} />
        )}
        {tab === "schedule" && (
          <ScheduleView work={work} openPlan={() => setTab("plan")} toast={showToast} />
        )}
      </div>
      <ChatPanel
        open={chat}
        lines={lines}
        suggestions={suggestions(state.plan, student, state.semesters.flatMap((x) => x.courses.filter(isSlot)).length)}
        onSuggest={suggest}
        onSend={send}
        onUndo={undo}
        canUndo={!!previous}
        onShow={show}
        busy={sending ? "Checking against the Bulletin…" : busy}
        left={left}
        aiDown={aiDown}
        hide={() => {
          setChat(false);
          setDocked(false);
        }}
      />
      {(!docked || !chat) && (
        <button
          className={`chat-reopen ${docked ? "phone-only" : ""}`}
          onClick={() => {
            setChat(true);
            setDocked(true);
          }}
        >
          <Icon name="spark" size={16} /> Ask GatorPath
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
      {toast && (
        <div className="toast">
          <Icon name="check" />
          {toast}
        </div>
      )}
    </div>
  );
}

type Built = { options: Options; plan: PlanResult; audit: Audit; filled: Assisted | null; why: string };

export default function App() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [style, setStyle] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [imported, setImported] = useState<ImportResult | null>(null);
  const [options, setOptions] = useState<Options>({});
  const [picks, setPicks] = useState<Picks>({ interests: [], after: [] });
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
          picks={picks}
          needs={needs}
          build={(chosen, chips) => {
            setOptions(chosen);
            setPicks(chips);
            go("building");
          }}
        />
      )}
      {screen === "building" && profile && (
        <BuildingScreen
          profile={profile}
          options={options}
          notes={imported ? [...new Set([...imported.cross_check, ...imported.warnings])] : []}
          back={() => go("goals")}
          done={(plan, audit, filled, why = "") => {
            setNeeds(plan.needs_input);
            if (plan.needs_input) return go("goals");
            setBuilt({ options, plan, audit, filled, why });
            go("app");
          }}
        />
      )}
      {screen === "app" && profile && built && (
        <AppWorkspace
          profile={profile}
          built={built}
          imported={imported}
          notes={imported ? [...new Set([...imported.cross_check, ...imported.warnings])] : []}
        />
      )}
      {style && <StyleGuide close={() => setStyle(false)} />}
      {screen !== "landing" && <Footer />}
    </div>
  );
}
