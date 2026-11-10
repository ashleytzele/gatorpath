import { useEffect, useState } from "react";
import { message, type Audit } from "./api";
import { FeedbackLink } from "./Feedback";

// ?demo shows the prototype's preview bars. The data stays real: they only force a state on top of it.
export const DEMO = new URLSearchParams(window.location.search).has("demo");
export type Screen = "landing" | "record" | "review" | "goals" | "building" | "app";
export type IconName =
  | "arrow"
  | "back"
  | "book"
  | "calendar"
  | "check"
  | "chevron"
  | "clock"
  | "copy"
  | "print"
  | "edit"
  | "file"
  | "flag"
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

export const iconPaths: Record<IconName, React.ReactNode> = {
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
  print: (
    <>
      <path d="M7 9V3h10v6M7 18H5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
      <rect x="7" y="14" width="10" height="7" rx="1" />
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
  flag: (
    <>
      <path d="M6 21V4M6 4h11l-2.5 4 2.5 4H6" />
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

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
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

export function Tooltip({ text }: { text: string }) {
  return (
    <span className="tooltip">
      <Icon name="info" size={15} />
      <span>{text}</span>
    </span>
  );
}

export const LOGO_SRC = "/gatorpath-logo.png?v=4"; // bump the number when the picture changes
export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="logo" aria-label="GatorPath">
      <span className="logo-mark">
        <img src={LOGO_SRC} alt="" />
      </span>
      {!compact && (
        <span>
          Gator<span>Path</span>
        </span>
      )}
    </div>
  );
}

export function Button({
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

export function StatusBadge({
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

export function Header({
  screen,
  onStyle,
}: {
  screen: Screen;
  onStyle: () => void;
}) {
  return (
    <header className="site-header">
      <div className="header-inner">
        <div className="brand-button">
          <Logo />
        </div>
        {screen !== "landing" && (
          <div className="header-actions">
            {screen === "app" && (
              <a className="header-link advisor-link" href={NAVIGATOR} target="_blank" rel="noreferrer">
                Ask an advisor
              </a>
            )}
          </div>
        )}
      </div>
    </header>
  );
}

export const NAVIGATOR = "https://sfsu.campus.eab.com/";
export const ASK_ADVISOR = "Ask an advisor in Navigator"; // the one name for the advising link
export const PRIVACY = "Your DPR PDF is never saved. Your record and plan stay in this browser tab through reloads and clear when you close the tab, or when you choose Clear my saved data. Gator AI sees your major, goal and courses, never your name, ID, grades or GPA. GatorPath counts visits, plans built and questions asked as anonymous daily totals, and keeps feedback you choose to send. It never keeps your record, grades or plan.";
/** Engine text in the student's words: "2027-spring" -> "Spring 2027", a requirement's id -> its title. */
export function plainText(text: string, audit?: Audit) {
  const titles = new Map((audit?.groups ?? []).map((g) => [g.id, g.title]));
  return text
    .replace(/\b(\d{4})-(spring|summer|fall|winter)\b/gi, (_, y: string, t: string) => `${t[0].toUpperCase()}${t.slice(1).toLowerCase()} ${y}`)
    .replace(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g, (id) => titles.get(id) ?? id.replace(/_/g, " "));
}
const steps = ["Your record", "Your goals", "Your plan"];
export function Stepper({ current }: { current: number }) {
  return (
    <nav className="stepper" aria-label="Planning progress">
      {steps.map((step, i) => (
        <div
          className={`step ${i + 1 === current ? "active" : ""} ${i + 1 < current ? "complete" : ""}`}
          aria-current={i + 1 === current ? "step" : undefined}
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

/** Set when the student clears this tab's saved data, so a save already waiting can't write it back. */
export const wiped = { on: false };

/** Removes everything this tab saved (record, goals, plan, chat) and goes back to the first page. Two steps, so a
 * stray click can't throw a plan away. */
function ClearSaved() {
  const [sure, setSure] = useState(false);
  if (!sure)
    return (
      <button type="button" className="pl-link" onClick={() => setSure(true)}>
        Clear my saved data
      </button>
    );
  return (
    <span role="alert">
      Remove your record and plan from this tab?{" "}
      <button
        type="button"
        className="pl-link"
        onClick={() => {
          wiped.on = true;
          try {
            sessionStorage.clear();
          } catch {
            /* storage is unavailable: nothing was saved */
          }
          window.location.assign("/");
        }}
      >
        Yes, clear it
      </button>{" "}
      <button type="button" className="pl-link" onClick={() => setSure(false)}>
        Keep it
      </button>
    </span>
  );
}

export function Footer() {
  return (
    <footer>
      <Icon name="info" size={15} />
      <span>
        Unofficial student-built tool, not affiliated with SF State. Questions about your plan?{" "}
        <a href={NAVIGATOR} target="_blank" rel="noreferrer">
          {ASK_ADVISOR}
        </a>{" "}
        · <ClearSaved /> · <FeedbackLink />
      </span>
    </footer>
  );
}

export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
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

export function Loading({ label }: { label: string }) {
  return (
    <div className="load-state" role="status">
      <span className="upload-orb spin">
        <Icon name="route" size={22} />
      </span>
      <strong>{label}</strong>
    </div>
  );
}

export function ErrorCard({ text, retry }: { text: string; retry?: () => void }) {
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

/** Fall and spring terms around today, a calendar for the dropdowns: `back` past ones, `ahead` to come. */
export function nearbyTerms(back: number, ahead: number) {
  const now = new Date();
  const fallNow = now.getMonth() >= 6;
  const index = now.getFullYear() * 2 + (fallNow ? 1 : 0);
  return Array.from({ length: back + ahead }, (_, i) => {
    const n = index - back + 1 + i;
    return `${Math.floor(n / 2)}-${n % 2 ? "fall" : "spring"}`;
  });
}


/** scrollIntoView that stays still for people who asked for less motion. */
export function calmScroll(el: Element | null | undefined, block: ScrollLogicalPosition = "start") {
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  el?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block });
}
