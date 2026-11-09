import { useEffect, useRef, useState } from "react";
import { assist, buildPlan, getAudit, message, type Assisted, type Audit, type Options, type PlanResult, type Profile } from "./api";
import { Button, ErrorCard, Icon, LOGO_SRC, calmScroll, useLoad } from "./ui";

const STEP_MS = 900; // one checklist line about every 0.9 s while the planner and the AI work

/** Waits for the plan, then for the AI's first fill of the open slots; the student can skip the AI. */
export default function BuildingScreen({
  profile,
  options,
  notes,
  done,
  back,
}: {
  profile: Profile;
  options: Options;
  notes: string[];
  done: (plan: PlanResult, audit: Audit, filled: Assisted | null, why?: string, skipped?: boolean) => void;
  back: () => void;
}) {
  const built = useLoad(
    () => Promise.all([buildPlan(profile, options), getAudit({ ...profile, ...options })]),
    [],
  );
  const [ai, setAi] = useState<{ filled: Assisted | null; why: string } | null>(null);
  const [shown, setShown] = useState(1);
  const [skipped, setSkipped] = useState(false); // the student chose their own electives: Gator AI isn't asked
  const [slow, setSlow] = useState(false); // Gator AI has run past the "about a minute" it promised
  const cancelled = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const plan = built.data?.[0];
  const needsAi = !!plan && !plan.needs_input && (notes.length > 0 || plan.semesters.some((s) => s.courses.some((c) => typeof c !== "string")));

  useEffect(() => {
    if (!plan) return;
    if (!needsAi) return setAi({ filled: null, why: "" });
    let stale = false; // this effect's own flag: StrictMode's simulated unmount must not drop the real answer
    const request = new AbortController();
    abort.current = request;
    assist({ ...profile, ...options }, plan.semesters, [], [], {}, notes, request.signal)
      .then((filled) => !stale && !cancelled.current && setAi({ filled, why: "" }))
      .catch((e) => !stale && !cancelled.current && setAi({ filled: null, why: message(e) })); // 503, 429 or any error: go on without it
    return () => {
      stale = true;
      request.abort(); // leaving this screen (or a StrictMode remount) stops the call too
    };
  }, [plan]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const t = setInterval(() => setShown((n) => n + 1), STEP_MS);
    return () => clearInterval(t);
  }, []);

  const units = (profile.completed ?? []).reduce((n, c) => n + (c.units ?? 0), 0);
  const steps = [
    units ? `Reading your DPR: ${units} units found` : "Reading your record",
    "Mapping your requirements",
    "Placing semesters from the official roadmap",
    "Putting prerequisites in order",
    "Balancing units per term",
    "Checking which terms offer each course",
  ];
  const planned = shown >= steps.length; // every planner line is out
  const waiting = planned && needsAi && !ai; // only Gator AI is left
  const card = useRef<HTMLElement>(null);
  useEffect(() => {
    if (waiting) calmScroll(card.current, "nearest"); // on a short window the card would sit below the fold
  }, [waiting]);
  useEffect(() => {
    if (!waiting) return;
    const t = setTimeout(() => setSlow(true), 60_000);
    return () => clearTimeout(t);
  }, [waiting]);
  const settled = !!plan && !!ai;
  const finished = planned && settled;
  const finish = (filled: Assisted | null, why = "") => built.data && done(built.data[0], built.data[1], filled, why, skipped);
  useEffect(() => {
    if (!finished) return;
    const t = setTimeout(() => finish(ai!.filled, ai!.why), STEP_MS);
    return () => clearTimeout(t);
  }, [finished]); // eslint-disable-line react-hooks/exhaustive-deps

  if (built.error) {
    return (
      <main id="main" tabIndex={-1} className="flow-page">
        <ErrorCard text={built.error} retry={built.retry} />
        <div className="flow-action">
          <Button kind="secondary" onClick={back}>
            Back to your goals
          </Button>
        </div>
      </main>
    );
  }
  const line = (text: string, running: boolean, key: string) => (
    <span key={key} className={running ? "checking" : ""}>
      {running ? <i /> : <Icon name="check" />} {text}
    </span>
  );
  return (
    <main id="main" tabIndex={-1} className="building-screen" aria-live="polite">  {/* a live region, not role=status: that would stop it being the main landmark */}
      <div className="building-orb">
        <span className="logo-mark building-logo"><img src={LOGO_SRC} alt="" /></span>
        <i />
        <i />
        <i />
      </div>
      <h1>Building your plan from the Bulletin…</h1>
      <p>Ordering prerequisites, balancing units, and checking course availability.</p>
      <div className="check-list">
        {steps.slice(0, Math.min(shown, steps.length)).map((s, i) => line(s, !planned && i === shown - 1, s))}
        {planned && needsAi && line(
          skipped ? "Skipped Gator AI: you'll choose your electives"
            : ai ? (ai.filled ? "Electives and GE chosen with Gator AI" : "Gator AI isn't available; you can choose electives yourself") : "Choosing electives and GE with Gator AI, about a minute",
          !ai,
          "ai",
        )}
        {finished && line("Checked against the Bulletin", false, "checked")}
        {finished && line("Your plan is ready · Opening your plan…", false, "ready")}
      </div>
      {waiting && (
        <section className="skip-card" aria-labelledby="skip-title" ref={card}>
          <h2 id="skip-title">Rather pick your own electives?</h2>
          <p>
            {slow
              ? "Still working. A long plan takes Gator AI a little longer. You can wait, or skip and choose from the courses that fit."
              : "Skip Gator AI and choose from the courses that fit. You can ask Gator AI for help later."}
          </p>
          <Button
            kind="secondary"
            onClick={() => {
              cancelled.current = true; // its answer is dropped, and the request stops
              abort.current?.abort();
              setSkipped(true);
              setAi({ filled: null, why: "" });
            }}
          >
            Skip, I’ll choose myself
          </Button>
        </section>
      )}
    </main>
  );
}
