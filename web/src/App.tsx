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
import { blockOf, changeLine, countSection, limitOf, offeredText, plannedLine, hours, splitWhy, suggestions, termLabel, unitText, warnedGroups, withPlanned, withoutUrls, type ChatLine } from "./logic";
import {
  ASK_ADVISOR, Button, DEMO, ErrorCard, Footer, Header, Icon, Loading, Logo, NAVIGATOR,
  Stepper, StatusBadge, calmScroll, plainText, useLoad, type Screen,
} from "./ui";

/** "record" is Your record with the plan beside it, reached from the Plan tab, not the tab bar. */
type Tab = "plan" | "electives" | "schedule" | "record";

const isDone = (g: Group) => g.status === "satisfied" || g.status === "waived";

/** An open section: a heading over a 2px rule, rows split by 1px lines. */
function Section({ title, count, children }: { title: string; count: string; children: React.ReactNode }) {
  return (
    <section className="el-section">
      <div className="el-head">
        <h2>{title}</h2>
        <span>{count}</span>
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
  const how = withoutUrls(a.how_to_book ?? ""); // the rules' words stay; their URLs are the links below
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
      {how && !links.some((l) => l.text.includes(how)) && <p className="pl-where">{how}</p>}
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
function ChoiceOptions({
  work,
  target,
  select,
  all,
}: {
  work: Work;
  target: Target;
  select: (code: string, option: Option) => void;
  all?: boolean; // the Electives & GE tab: also the ones past the first three, and why the rest can't be taken
}) {
  const found = useLoad(
    () => getElectives(work.student, target.group, { semesters: work.semesters }, target.term),
    [target.group, target.term, target.replacing],
  );
  // ponytail: the first three that fit, in the server's order
  const others = (found.data?.options ?? []).filter((o) => o.code !== target.replacing);
  const fits = others.filter((o) => o.readiness !== "blocked");
  const blocked = all ? others.filter((o) => o.readiness === "blocked") : [];
  const options = fits.slice(0, 3);
  const more = all ? fits.slice(3) : [];
  const term = termLabel(target.term);
  const row = (o: Option) => {
    const covers = o.also_covers.map((id) => work.audit.groups.find((g) => g.id === id)?.title ?? id);
    return (
      <li key={o.code}>
        <b>{o.code}</b>
        <span>
          {o.title}
          <small>
            {" · "}
            {o.readiness === "check"
              ? `Check: ${plainText(o.cannot_check?.join("; ") || o.note || "its prerequisites", work.audit)}`
              : "Ready"}
          </small>
          {all && <small className="pl-opt-line">{offeredText(o.offered)}</small>}
          {!!covers.length && <small className="pl-opt-line">Also counts for {covers.join(", ")}</small>}
        </span>
        <button type="button" className="pl-link" disabled={work.aiBusy} onClick={() => select(o.code, o)}>
          Select<span className="sr-only"> {o.code}</span>
        </button>
      </li>
    );
  };
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
      {!!options.length && <ul className="pl-options">{options.map(row)}</ul>}
      {!!more.length && (
        <details className="pl-more">
          <summary>{more.length} more that fit</summary>
          <ul className="pl-options">{more.map(row)}</ul>
        </details>
      )}
      {!!blocked.length && (
        <details className="pl-more">
          <summary>
            {blocked.length} not possible {term}
          </summary>
          <ul className="pl-options">
            {blocked.map((o) => (
              <li key={o.code}>
                <b>{o.code}</b>
                <span>
                  {o.title}
                  <small className="pl-opt-line">
                    {plainText([...(o.blocked_by ?? []), o.not_offered].filter(Boolean).join("; ") || "Not possible that term", work.audit)}
                  </small>
                </span>
              </li>
            ))}
          </ul>
        </details>
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
          {coverage &&
            `With ${choices ? "the courses planned so far" : "this plan"}, ${coverage.done} of ${coverage.total} requirements are complete. `}
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
        <Button kind="secondary" icon="print" onClick={() => window.print()}>
          Print my plan
        </Button>
      </div>
    </div>
  );
}

type ChoiceRow = { key: string; id: string; title: string; term: string; units?: number; pick?: Pick };

function ChoiceRequirementRows({
  rows,
  work,
  open,
  setOpen,
  select,
}: {
  rows: ChoiceRow[];
  work: Work;
  open: string;
  setOpen: (key: string) => void;
  select: (target: Target, code: string, option: Option) => void;
}) {
  const back = useRef(""); // the row a Select came from: focus goes back to it once the check is done
  useEffect(() => {
    if (work.aiBusy || !back.current) return;
    document.querySelector<HTMLElement>(`[data-row="${back.current}"]`)?.focus();
    back.current = "";
  }, [work.aiBusy]);
  return (
    <ul className="el-rows">
      {rows.map((r) => {
        const key = r.key;
        const target = { group: r.id, term: r.term, title: r.title, replacing: r.pick?.code };
        const about = r.pick && (work.info[r.pick.code] ?? work.audit.courses[r.pick.code]);
        return (
          <li key={key}>
            <div className="el-row">
              <span className="el-req">{r.title}</span>
              <span className="el-course">
                {r.pick ? (
                  <>
                    <b>{r.pick.code}</b> {about?.title}
                  </>
                ) : (
                  <span className="el-none">Not chosen yet</span>
                )}
                {!!r.pick?.covers.length && <small> · Counts twice</small>}
              </span>
              <span className="el-term">{termLabel(r.term)}</span>
              <button
                type="button"
                className="pl-link"
                data-row={key}
                aria-expanded={open === key}
                disabled={work.aiBusy}
                onClick={(e) => {
                  e.currentTarget.focus(); // Safari doesn't focus a clicked button; the card returns focus here
                  setOpen(open === key ? "" : key);
                }}
              >
                {r.pick ? "Swap" : "Choose"}
                <span className="sr-only"> {r.title}</span>
              </button>
            </div>
            {open === key && (
              <FloatingCard label={`Options for ${r.title}`} onClose={() => setOpen("")}>
                <div className="pl-card">
                  <h3>{r.title}</h3>
                  <p className="pl-card-sub">
                    {r.pick
                      ? `In your plan: ${r.pick.code}${about?.title ? ` · ${about.title}` : ""}`
                      : r.units
                        ? `Open choice · ${unitText(r.units)}`
                        : "Open choice"}
                  </p>
                  <ChoiceOptions
                    work={work}
                    target={target}
                    all
                    select={(code, option) => {
                      back.current = key;
                      setOpen("");
                      select(target, code, option);
                    }}
                  />
                </div>
              </FloatingCard>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function ElectivesView({
  work,
  select,
}: {
  work: Work;
  select: (target: Target, code: string, option: Option) => void;
}) {
  const { audit, check, info, picks, semesters, student } = work;
  const [open, setOpen] = useState(""); // the row whose card is open: one at a time
  useEffect(() => setOpen(""), [semesters]); // a change moves rows under an open card
  // In plan order, keyed by place: a choice filled in place keeps its row. ponytail: a pick is always in its term's
  // courses (the server keeps only those; choose and Finish sooner move both), so none is left out here.
  const rows: ChoiceRow[] = semesters.flatMap((s) =>
    s.courses.flatMap((c, i): ChoiceRow[] => {
      const key = `${s.term}|${i}`;
      if (isSlot(c)) return [{ key, id: c.slot, title: slotLabel(c, audit), term: s.term, units: c.units }];
      const pick = picks.find((p) => p.code === c && p.term === s.term);
      return pick ? [{ key, id: pick.group, title: slotLabel({ slot: pick.group, units: 0 }, audit), term: s.term, pick }] : [];
    }),
  );
  const major = rows.filter((r) => audit.groups.find((g) => g.id === r.id)?.kind === "major");
  const ge = rows.filter((r) => r.id.startsWith("ge_"));
  const free = rows.filter((r) => r.id === "elective");
  const studies = rows.filter((r) => !major.includes(r) && !ge.includes(r) && !free.includes(r));
  const openCount = rows.filter((r) => !r.pick).length;
  const count = (list: ChoiceRow[]) => `${list.filter((r) => r.pick).length} chosen, ${list.filter((r) => !r.pick).length} to go`;
  const short = audit.groups.find((g) => g.min_units_from && !isDone(g));
  const inSubject = short?.min_units_from
    ? picks
        .filter((p) => p.group === short.id && p.code.startsWith(short.min_units_from!.subject))
        .reduce((total, p) => total + unitsOf(p.code, info), short.min_units_from.done)
    : 0;
  const planned = plannedLine(
    short?.units_done,
    short?.units_needed,
    rows.filter((r) => r.id === short?.id).map((r) => (r.pick ? unitsOf(r.pick.code, info) : (r.units ?? 0))),
  );
  const section = (title: string, list: ChoiceRow[], extra?: React.ReactNode) =>
    !!list.length && (
      <Section title={title} count={count(list)}>
        {extra}
        <ChoiceRequirementRows rows={list} work={work} open={open} setOpen={setOpen} select={select} />
      </Section>
    );
  return (
    <div className="app-content">
      <div className="page-title">
        <h1>Electives & GE</h1>
        <p>
          {picks.some((p) => p.ai) && student.goal && student.goal !== "Undecided" && `Picked around your focus: ${student.goal}. `}
          {openCount ? `${openCount} of ${rows.length} choices still open.` : "All choices made."} Swap or Choose a row to see
          the courses that fit, or ask the chat.
        </p>
      </div>
      {!check.valid && <ProblemPanel errors={check.errors} audit={audit} ask={work.ask} />}
      {work.busy && <Loading label={work.busy} />}
      {work.failed && <ErrorCard text={work.failed} />}
      {section(
        "Major electives",
        major,
        short?.min_units_from && (
          <div className="csc-unit-progress">
            <div>
              <b>
                {planned ? `${planned}, ` : ""}
                {inSubject} of {short.min_units_from.units} in {short.min_units_from.subject}
              </b>
              <span>{Math.min(100, Math.round((inSubject / short.min_units_from.units) * 100))}%</span>
            </div>
            <div>
              <i style={{ width: `${Math.min(100, (inSubject / short.min_units_from.units) * 100)}%` }} />
            </div>
          </div>
        ),
      )}
      {section("GE still needed", ge)}
      {section("SF State Studies & American Institutions", studies)}
      {section("Free electives", free)}
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
  s.seats_open
    ? `${s.seats_open} seats open`
    : s.waitlist_open
      ? `Full · ${s.waitlist_open} waitlist ${s.waitlist_open === 1 ? "spot" : "spots"}`
      : "Full";
const HOUR_PX = 60;
const hourName = (h: number) => `${h % 12 || 12} ${h < 12 ? "AM" : "PM"}`;
/** "MATH 226 01" -> "MATH 226" */
const courseOf = (x: string) => x.slice(0, x.lastIndexOf(" "));
type Look = { code: string; nbr: string };

function ScheduleView({
  work,
  openElectives,
  toast,
}: {
  work: Work;
  openElectives: () => void;
  toast: (x: string) => void;
}) {
  const first = work.semesters[0];
  const codes = first.courses.filter((c): c is string => !isSlot(c));
  const open_choices = first.courses.filter((c) => isSlot(c)).length;
  const label = termLabel(first.term);
  const online = work.picks.filter((p) => p.online && p.term === first.term).map((p) => p.code);
  const keep = work.sections[first.term] ?? [];
  const result = useLoad(
    () => getSections(first.term, codes, online, keep),
    [first.term, codes.join(), online.join(), keep.join()],
  );
  const [open, setOpen] = useState(""); // the course whose Other sections card is open: one at a time
  const [hover, setHover] = useState<Look | null>(null); // pointed at or focused, dashed on the week
  const [pinned, setPinned] = useState<Look | null>(null); // See on week: stays until Select or Cancel
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
  const unpublished = !Object.keys(r.sections).length && !!r.unknown.length;
  const problems = [
    ...r.not_offered.map((c) => `${c} isn’t offered in ${label}.`),
    ...(r.schedule === null && r.always_clash.length
      ? [`${r.always_clash[0].join(" and ")} always overlap, so no combination fits.`]
      : []),
  ];
  const lookup = (l: Look | null) => (l ? r.sections[l.code]?.find((s) => s.class_nbr === l.nbr) : undefined);
  const peek = hover && lookup(hover) ? hover : pinned && lookup(pinned) ? pinned : null;
  const shown = lookup(peek);
  const clashing = (shown?.clashes_with ?? []).map(courseOf);
  const timed = (c: (typeof classes)[number], i: number, s: Section, look = "") =>
    s.meetings.flatMap((m) =>
      hours(m) && m.days ? m.days.split(" ").map((day) => ({ c, i, s, m, day, look })) : [],
    );
  const ci = (code: string) => classes.findIndex((c) => c.code === code);
  const blocks = [
    ...classes.flatMap((c, i) =>
      c.picked.flatMap((s) =>
        timed(c, i, s, c.code === peek?.code ? "faded" : clashing.includes(c.code) ? "clash" : ""),
      ),
    ),
    ...(shown && peek
      ? timed(classes[ci(peek.code)], ci(peek.code), shown, clashing.length ? "preview clash" : "preview")
      : []),
  ];
  // The week runs from the first class hour to the last. ponytail: a hover preview outside it is clipped; See on week widens it.
  const span = [
    ...classes.flatMap((c) => c.picked.flatMap((s) => s.meetings)),
    ...(lookup(pinned) ? lookup(pinned)!.meetings : []),
  ].flatMap((m) => {
    const t = hours(m);
    return t && m.days ? [t] : [];
  });
  const start = span.length ? Math.floor(Math.min(...span.map((t) => t.start))) : 8;
  const end = span.length ? Math.ceil(Math.max(...span.map((t) => t.end))) : 9;
  const dayIndex = (day: string) => CALENDAR_DAYS.findIndex(([, code]) => code === day);
  const units = codes.reduce((n, c) => n + (parseFloat(String((work.info[c] ?? work.audit.courses[c])?.units)) || 0), 0);
  const untimed = classes.filter((c) => !c.picked.some((s) => s.meetings.some((m) => m.days && hours(m))));
  const after = work.semesters[1];

  const toWeek = (focusBar: boolean) =>
    setTimeout(() => {
      calmScroll(document.querySelector(".schedule-controls"));
      if (focusBar) document.querySelector<HTMLElement>(".peek-bar button")?.focus({ preventScroll: true });
    }, 0); // after the card has closed and given focus back
  const cancel = () => {
    const back = pinned?.code;
    setPinned(null);
    setHover(null);
    setTimeout(() => document.querySelector<HTMLElement>(`[data-others="${back}"]`)?.focus(), 0);
  };
  const use = async (look: Look) => {
    const section = lookup(look);
    if (!section) return;
    const theirs = r.sections[look.code].map((s) => s.class_nbr); // one choice per class
    const next = [...keep.filter((n) => !theirs.includes(n)), section.class_nbr];
    setTrying(true);
    try {
      const tried = await getSections(first.term, codes, online, next);
      if (!tried.schedule) {
        const other = tried.always_clash.flat().filter((c) => c !== look.code);
        return toast(`${look.code} ${section.section} can’t fit: it overlaps every section of ${other.join(", ")}`);
      }
      setPinned(null);
      setHover(null);
      setOpen("");
      work.setSections(first.term, next);
    } catch (e) {
      toast(message(e));
    } finally {
      setTrying(false);
    }
  };
  const fitText = (s: Section) =>
    s.clashes_with ? (s.clashes_with.length ? `Clashes with ${s.clashes_with.join(", ")}` : "Fits") : "";
  const roomType = (s: Section, m: { where?: string }) => [m.where, s.component].filter(Boolean).join(" · ");
  return (
    <div className="app-content">
      <div className="schedule-title">
        <div>
          <h1>Your {label} schedule</h1>
          <p>One clash-free combination based on your plan.</p>
        </div>
      </div>
      {unpublished ? (
        <div className="schedule-problem-frame unpublished">
          <span>
            <Icon name="clock" />
          </span>
          <div>
            <h2>{label} schedule isn’t published yet</h2>
            <p>SF State hasn’t posted this term’s classes yet, so there are no sections to show. Your plan is fine.</p>
            <a href={CLASS_SEARCH} target="_blank" rel="noreferrer">
              Check Class Search <Icon name="arrow" size={13} />
            </a>
          </div>
        </div>
      ) : (
        <>
          {!!problems.length && (
            <p className="sched-problem" role="status">
              <Icon name="warning" size={15} /> <span>{problems.join(" ")}</span>
              <button
                type="button"
                disabled={work.aiBusy}
                onClick={() => work.ask(`Please move one of my ${label} classes so my schedule has no time clashes. ${problems.join(" ")}`)}
              >
                Ask the chat to move one
              </button>
            </p>
          )}
          {r.unknown.map((code) => (
            <p className="online-note" key={code}>
              <Icon name="warning" size={15} /> <b>{code}</b> isn’t in our schedule data. Check{" "}
              <a href={CLASS_SEARCH} target="_blank" rel="noreferrer">Class Search</a>.
            </p>
          ))}
          {open_choices > 0 && (
            <p className="online-note">
              <Icon name="info" size={15} /> {open_choices === 1 ? "One choice isn’t" : `${open_choices} choices aren’t`} made
              yet, so {open_choices === 1 ? "it isn’t" : "they aren’t"} here.{" "}
              <button type="button" className="inline-link" onClick={openElectives}>
                Choose in Electives &amp; GE
              </button>
            </p>
          )}
          {!!classes.length && (
            <>
              <div className="schedule-controls">
                <div>
                  <b>
                    No time clashes · {classes.length} {classes.length === 1 ? "class" : "classes"} · {unitText(units)}
                  </b>
                </div>
                {r.scraped_at && (
                  <span className="seats-date">
                    Seats as of {new Date(r.scraped_at).toLocaleDateString()} ·{" "}
                    <a href={CLASS_SEARCH} target="_blank" rel="noreferrer">
                      Class Search
                    </a>
                  </span>
                )}
              </div>
              {pinned && shown && lookup(pinned) === shown && (
                <div className={`peek-bar${clashing.length ? " clash" : ""}`} role="status">
                  <p>
                    <b>
                      Previewing {pinned.code} section {shown.section}
                    </b>{" "}
                    · {when(shown)}
                    {fitText(shown) && ` · ${fitText(shown)}`}
                  </p>
                  <div>
                    <Button onClick={() => use(pinned)} disabled={trying || work.aiBusy}>
                      {clashing.length ? "Select and move others" : `Select section ${shown.section}`}
                    </Button>
                    <Button kind="ghost" onClick={cancel}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
              {!!blocks.length && (
                <div className="calendar-card hourly">
                  <div className="calendar-head">
                    {["TIME", "MON", "TUE", "WED", "THU", "FRI"].map((x) => (
                      <span key={x}>{x}</span>
                    ))}
                  </div>
                  <div className="calendar-body" style={{ height: (end - start) * HOUR_PX }}>
                    <div className="times">
                      {Array.from({ length: end - start + 1 }, (_, k) => (
                        <span key={k} style={{ top: k * HOUR_PX }}>
                          {hourName(start + k)}
                        </span>
                      ))}
                    </div>
                    <div className="day-grid" style={{ "--hp": `${HOUR_PX}px` } as React.CSSProperties}>
                      {[0, 1, 2, 3, 4].map((x) => (
                        <i key={x} />
                      ))}
                      {blocks
                        .filter((b) => dayIndex(b.day) >= 0)
                        .map((b) => {
                          const pos = blockOf(b.m, start, HOUR_PX);
                          if (!pos || pos.top < 0 || pos.top + pos.height > (end - start) * HOUR_PX) return null;
                          return (
                            <button
                              type="button"
                              className={`cal-block c${b.i % 3} ${b.look}`}
                              key={`${b.look}${b.s.class_nbr}${b.m.time}${b.day}`}
                              style={{ top: pos.top + 1, height: pos.height - 3, left: `calc(${dayIndex(b.day)} * 20% + 4px)` }}
                              aria-label={`${b.c.code} ${b.m.time}. Open its other sections`}
                              onClick={(e) => {
                                e.currentTarget.focus();
                                setOpen(b.c.code);
                                setTimeout(() => calmScroll(document.querySelector(`[data-course="${b.c.code}"]`), "center"), 0);
                              }}
                            >
                              <b>
                                {b.c.code} {b.m.time}
                              </b>
                              <span>{roomType(b.s, b.m)}</span>
                            </button>
                          );
                        })}
                    </div>
                  </div>
                </div>
              )}
              {untimed.map((c) => (
                <p className="online-note" key={c.code}>
                  <Icon name="info" size={15} /> <b>{c.code}</b> has no set meeting time, so it isn’t on the week.
                </p>
              ))}
              <div className="mobile-day-list">
                {CALENDAR_DAYS.map(([day, code]) => (
                  <div key={day}>
                    <b>{day}</b>
                    <section>
                      {blocks
                        .filter((b) => b.day === code)
                        .sort((a, b) => hours(a.m)!.start - hours(b.m)!.start)
                        .map((b) => (
                          <span className={b.look} key={`${b.look}${b.s.class_nbr}${b.m.time}`}>
                            <i className={`class-dot c${b.i % 3}`} />
                            <strong>{b.c.code}</strong>
                            {b.m.time} · {roomType(b.s, b.m)}
                          </span>
                        ))}
                    </section>
                  </div>
                ))}
              </div>
              <h2 className="sched-head">Your sections</h2>
              <div className="section-list">
                {classes.map((c) => {
                  const [main, ...linked] = c.picked;
                  const theirs = r.sections[c.code].map((s) => s.class_nbr);
                  const mine = keep.some((n) => theirs.includes(n));
                  return (
                    <article className="section-detail" key={c.code} data-course={c.code}>
                      <div className="section-main">
                        <span>
                          <b>{c.code}</b>
                          {(work.info[c.code] ?? work.audit.courses[c.code])?.title && (
                            <span className="sd-title">{(work.info[c.code] ?? work.audit.courses[c.code]).title}</span>
                          )}
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
                          <div className="other-wrap">
                            <button
                              type="button"
                              className="other-btn"
                              data-others={c.code}
                              aria-expanded={open === c.code}
                              onClick={(e) => {
                                e.currentTarget.focus(); // Safari doesn't focus a clicked button; the card returns focus here
                                setOpen(open === c.code ? "" : c.code);
                              }}
                            >
                              Other sections <Icon name="chevron" />
                            </button>
                            {open === c.code && (
                              <FloatingCard label={`Other sections of ${c.code}`} onClose={() => { setOpen(""); setHover(null); }}>
                                <h3 className="os-title">Other sections of {c.code}</h3>
                                <ul className="os-rows">
                                  {c.others.map((o) => {
                                    const look = { code: c.code, nbr: o.class_nbr };
                                    return (
                                      <li
                                        key={o.class_nbr}
                                        onMouseEnter={() => setHover(look)}
                                        onMouseLeave={() => setHover(null)}
                                        onFocus={() => setHover(look)}
                                        onBlur={() => setHover(null)}
                                      >
                                        <p>
                                          <b>Section {o.section}</b> · {when(o)} · Class #{o.class_nbr}
                                        </p>
                                        <p className="os-sub">
                                          {o.mode}
                                          <Instructors section={o} /> · {seats(o)}
                                        </p>
                                        {!!fitText(o) && (
                                          <p className={o.clashes_with?.length ? "os-clash" : "os-fits"}>{fitText(o)}</p>
                                        )}
                                        <div className="os-actions">
                                          <button
                                            type="button"
                                            className="button ghost"
                                            onClick={() => {
                                              setPinned(look);
                                              setHover(null);
                                              setOpen("");
                                              toWeek(true);
                                            }}
                                          >
                                            See on week
                                          </button>
                                          <button
                                            type="button"
                                            className="button secondary"
                                            disabled={trying || work.aiBusy}
                                            onClick={() => use(look)}
                                          >
                                            {o.clashes_with?.length ? "Select and move others" : "Select"}
                                          </button>
                                        </div>
                                      </li>
                                    );
                                  })}
                                </ul>
                              </FloatingCard>
                            )}
                          </div>
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
            </>
          )}
          {after && (
            <p className="online-note">
              <Icon name="info" size={15} /> {termLabel(after.term)} classes will be listed when SF State publishes them. Check{" "}
              <a href={CLASS_SEARCH} target="_blank" rel="noreferrer">Class Search</a> then.
            </p>
          )}
          {r.warnings
            .filter((w) => !w.startsWith("Class Search as of"))
            .map((w) => (
              <div className="schedule-note" key={w}>
                <Icon name="warning" /> <span>{plainText(w, work.audit)}</span>
              </div>
            ))}
          {!!classes.length && (
            <div className="plan-actions">
              <Button kind="secondary" icon="print" onClick={() => window.print()}>
                Print my schedule
              </Button>
            </div>
          )}
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
const applyAnswer = <T extends { semesters: Semester[]; plan: PlanResult; options: Partial<Profile>; info: Record<string, CourseInfo>; picks: Pick[]; sections: Record<string, string[]> }>(
  state: T,
  r: Assisted,
) => ({
  ...state,
  semesters: r.semesters.map((s) => ({ ...state.semesters.find((o) => o.term === s.term), ...s })),
  check: r.check,
  picks: r.picks.map((p) => {
    const had = state.picks.find((q) => q.code === p.code);
    return { ...p, ai: had ? had.ai : true }; // what the AI added; the student's own choices stay theirs
  }),
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
  const [left, setLeft] = useState(() => built.filled?.left ?? limitOf(built.why)); // the first fill may have hit a limit
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
    else setLeft(limitOf(m, left));
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
      calmScroll(rows[0], "center");
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
              locked={work.aiBusy}
              leave={{ label: "Back to your plan", go: () => go("plan") }}
            />
          </div>
        )}
        {tab === "electives" && (
          <ElectivesView work={work} select={choose} />
        )}
        {tab === "schedule" && (
          <ScheduleView work={work} openElectives={() => setTab("electives")} toast={showToast} />
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
