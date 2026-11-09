import { useEffect, useRef, useState } from "react";
import { assist, buildPlan, getAudit, message, type Assisted, type Audit, type Options, type PlanResult, type Profile } from "./api";
import { Button, ErrorCard, Icon, useLoad } from "./ui";

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
  done: (plan: PlanResult, audit: Audit, filled: Assisted | null, why?: string) => void;
  back: () => void;
}) {
  const built = useLoad(
    () => Promise.all([buildPlan(profile, options), getAudit({ ...profile, ...options })]),
    [],
  );
  const [ai, setAi] = useState<{ filled: Assisted | null; why: string } | null>(null);
  const [shown, setShown] = useState(1);
  const cancelled = useRef(false);
  const plan = built.data?.[0];
  const needsAi = !!plan && !plan.needs_input && (notes.length > 0 || plan.semesters.some((s) => s.courses.some((c) => typeof c !== "string")));

  useEffect(() => {
    if (!plan) return;
    if (!needsAi) return setAi({ filled: null, why: "" });
    let stale = false; // this effect's own flag: StrictMode's simulated unmount must not drop the real answer
    assist({ ...profile, ...options }, plan.semesters, [], [], {}, notes)
      .then((filled) => !stale && !cancelled.current && setAi({ filled, why: "" }))
      .catch((e) => !stale && !cancelled.current && setAi({ filled: null, why: message(e) })); // 503, 429 or any error: go on without it
    return () => {
      stale = true;
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
  const settled = !!plan && !!ai;
  const finished = planned && settled;
  const finish = (filled: Assisted | null, why = "") => built.data && done(built.data[0], built.data[1], filled, why);
  useEffect(() => {
    if (!finished) return;
    const t = setTimeout(() => finish(ai!.filled, ai!.why), STEP_MS);
    return () => clearTimeout(t);
  }, [finished]); // eslint-disable-line react-hooks/exhaustive-deps

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
  const line = (text: string, running: boolean, key: string) => (
    <span key={key} className={running ? "checking" : ""}>
      {running ? <i /> : <Icon name="check" />} {text}
    </span>
  );
  return (
    <main className="building-screen" role="status">
      <div className="building-orb">
        <span className="logo-mark building-logo"><img src="/gatorpath-logo.png?v=4" alt="" /></span>
        <i />
        <i />
        <i />
      </div>
      <h1>Building your plan from the Bulletin…</h1>
      <p>Ordering prerequisites, balancing units, and checking course availability.</p>
      <div className="check-list">
        {steps.slice(0, Math.min(shown, steps.length)).map((s, i) => line(s, !planned && i === shown - 1, s))}
        {planned && needsAi && line(
          ai ? (ai.filled ? "Electives and GE chosen with Gator AI" : "Gator AI isn't available; you can choose electives yourself") : "Choosing electives and GE with Gator AI, about a minute",
          !ai,
          "ai",
        )}
        {finished && line("Checked against the Bulletin", false, "checked")}
        {finished && line("Your plan is ready · Opening your plan…", false, "ready")}
      </div>
      {!finished && <div className="skeleton-row">
        <i />
        <i />
        <i />
      </div>}
      {planned && needsAi && !ai && (
        <Button kind="secondary" onClick={() => { cancelled.current = true; finish(null); }}>
          Skip and choose my electives myself →
        </Button>
      )}
    </main>
  );
}
