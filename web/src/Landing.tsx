import { Icon, Logo, NAVIGATOR } from "./ui";

const LINKS = [
  ["what", "What you get"],
  ["how", "How it works"],
  ["questions", "Questions"],
] as const;

// Each icon is one path in a 24px box.
const FEATURES = [
  { title: "Your record, read for you", text: "Upload your DPR and check every requirement, course, grade and unit on one clear page.", icon: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6" },
  { title: "A plan that passes the Bulletin", text: "Every term is checked: prerequisites, unit loads, and when each course is usually offered.", icon: "M5 12l4 4L19 6" },
  { title: "Ask, and it changes", text: "Finish sooner, lighter terms, a different GE: ask the chat. Every change is checked again before it lands.", icon: "M4 5h16v11H9l-5 4z" },
  { title: "Next term’s schedule", text: "Sections with no time clashes, with rooms, instructors and class numbers ready for registration.", icon: "M4 6h16v14H4zM4 10h16M9 3v4M15 3v4" },
];

const POINTS = [
  ["What’s left, at a glance.", "Open any requirement to see its courses and grades."],
  ["The class that sets your date.", "Your longest prerequisite chain, named."],
  ["Ready to register.", "Next term’s sections, times, rooms and class numbers."],
  ["Ready for your advisor.", "Print it, with the right office for each question."],
];

const DOES = [
  "Reads your DPR and shows what’s left",
  "Plans every term to graduation",
  "Checks the plan against the Bulletin",
  "Builds next term’s schedule with no time clashes",
];
const SFSU = [
  ["Your official degree audit", "your DPR"],
  ["Approvals, substitutions and exceptions", "your advisor"],
  ["Registration", "Student Center"],
];

const STEPS = [
  ["Upload your DPR", "We read your courses, grades, and what your degree still needs. You check it first."],
  ["Tell us your goals", "Your interests, when you want to finish, and how many units you can take."],
  ["Get your plan and schedule", "Every term, checked against the Bulletin, and next term’s sections ready to register."],
];

const FAQ = [
  ["Is GatorPath official?", "No. GatorPath is a student-built planning aid. Your DPR is the official record, and an advisor has the final word on your degree."],
  ["Is my data safe?", "Your DPR PDF is read in memory and never saved. Your record and plan stay in this browser tab's session storage so a reload keeps your work; they clear when you close the tab or choose Clear my saved data. Gator AI sees your major, goal and courses, never your name, ID, grades or GPA. It only learns a grade if you type one in the chat."],
  ["What’s a DPR, and how do I get it?", "Your Degree Progress Report shows your completed courses and what your degree still requires. In Student Center, open Degree Progress Report, click Expand All and View All, then Print → Save as PDF."],
  ["Does it work for my major?", "It has the 2026–27 rules for the bachelor’s programs listed when you choose your goals, written from the Bulletin. Always compare your plan with your DPR and an advisor."],
  ["Does it use AI?", "Gator AI chooses electives and answers in the chat (Claude Haiku). Planning and every check use Bulletin rules. Gator AI has hourly and daily limits; planning works without it."],
];

export function Landing({ start }: { start: () => void }) {
  return (
    <>
      <a className="skip-link" href="#top">Skip to the main content</a>
      <header className="ld-nav">
        <div className="ld-nav-inner">
          <a href="#top" className="ld-logo" aria-label="GatorPath">
            <Logo />
          </a>
          <nav className="ld-links" aria-label="On this page">
            {LINKS.map(([id, label]) => (
              <a href={`#${id}`} key={id}>{label}</a>
            ))}
          </nav>
          <button className="ld-btn ld-btn-green ld-btn-sm" onClick={start}>Start planning</button>
        </div>
      </header>
      <main id="top" tabIndex={-1} className="ld">
        <section className="ld-hero">
          <p className="ld-label">For SF State students</p>
          <h1>Plan your path to graduation in 5 minutes.</h1>
          <p className="ld-lede">
            Upload your DPR, tell us your goals, and get a semester-by-semester plan checked against
            the Bulletin, plus next term’s schedule with no time clashes.
          </p>
          <div className="ld-actions">
            <button className="ld-btn ld-btn-green" onClick={start}>
              Start planning <Icon name="arrow" size={18} />
            </button>
            <a className="ld-btn ld-btn-outline" href="#demo">
              <span className="ld-tri" aria-hidden="true" />
              Watch the demo
            </a>
          </div>
          <p className="ld-fine">No account needed. Your DPR PDF is never saved.</p>
        </section>

        <section id="demo" className="ld-demo" aria-label="Demo video">
          <div className="ld-frame">
            <video className="ld-demo-video" controls playsInline preload="none" poster="/landing-upload.jpg" aria-label="GatorPath walkthrough from DPR upload to a plan">
              <source src="/gatorpath-demo.mp4" type="video/mp4" />
              Your browser can’t play this video. You can still start planning below.
            </video>
          </div>
          <p className="ld-caption">A short walkthrough with a fictional student, starting at DPR upload.</p>
        </section>

        <section className="ld-facts" aria-label="About GatorPath">
          <ul>
            <li>✓ Built from the 2026–27 SF State Bulletin</li>
            {/* the count is the number of rules/programs/2026-27/*.yaml; tests/test_api.py compares it */}
            <li>✓ Rules for 108 majors</li>
            <li>✓ Every plan checked</li>
            <li>✓ Your DPR PDF is never saved</li>
          </ul>
        </section>

        <section id="what" className="ld-sec">
          <p className="ld-label">What you get</p>
          <h2>Everything your DPR leaves you to work out.</h2>
          <p className="ld-sub">Your DPR tells you what’s done. GatorPath works out what to take, and when.</p>
          <div className="ld-grid2">
            {FEATURES.map((f) => (
              <div className="ld-feature" key={f.title}>
                <span className="ld-icon" aria-hidden="true">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d={f.icon} />
                  </svg>
                </span>
                <h3>{f.title}</h3>
                <p>{f.text}</p>
              </div>
            ))}
          </div>
          <figure className="ld-schedule-shot">
            <img src="/landing-weekly.jpg" alt="A sample weekly class calendar with course times and rooms" loading="lazy" />
            <figcaption>See class times, rooms, and sections together before registration.</figcaption>
          </figure>
        </section>

        <section className="ld-band" aria-labelledby="route">
          <div className="ld-split ld-sec">
            <figure className="ld-route-box">
              <img src="/landing-plan.jpg" alt="A sample term-by-term GatorPath plan for a fictional student" loading="lazy" />
              <figcaption>Sample plan for a fictional student</figcaption>
            </figure>
            <div>
              <p className="ld-label">Your route</p>
              <h2 id="route">See your whole route.</h2>
              <p className="ld-sub">Every term to graduation on one page, and the reason each class sits where it does.</p>
              <ul className="ld-points">
                {POINTS.map(([lead, text]) => (
                  <li key={lead}><span aria-hidden="true" /><span><b>{lead}</b> {text}</span></li>
                ))}
              </ul>
              <button className="ld-btn ld-btn-dark" onClick={start}>Start planning</button>
            </div>
          </div>
        </section>

        <section className="ld-sec" aria-labelledby="limits">
          <p className="ld-label">Honest limits</p>
          <h2 id="limits">Helpful, not official.</h2>
          <div className="ld-cols">
            <div>
              <h3>GatorPath does</h3>
              <ul>
                {DOES.map((t) => (
                  <li key={t}><span className="yes" aria-hidden="true">✓</span>{t}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3>Only SF State does</h3>
              <ul>
                {SFSU.map(([t, where]) => (
                  <li key={t}><span aria-hidden="true">→</span><span>{t} <span className="where">· {where}</span></span></li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <section id="how" className="ld-how" aria-labelledby="howh">
          <div className="ld-sec">
            <p className="ld-label">How it works</p>
            <h2 id="howh">Three steps, about five minutes.</h2>
            <ol className="ld-steps">
              {STEPS.map(([title, text], i) => (
                <li key={title}>
                  <div className="ld-step-top">
                    <span className={`ld-step-dot ${i === 0 ? "active" : ""}`} aria-hidden="true">{i + 1}</span>
                    {i < STEPS.length - 1 && <span className="ld-stepline" aria-hidden="true" />}
                  </div>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="questions" className="ld-sec ld-faq" aria-labelledby="qh">
          <h2 id="qh">Questions</h2>
          <div className="ld-faq-list">
            {FAQ.map(([q, a]) => (
              <details key={q}>
                <summary>{q}<span className="ld-plus" aria-hidden="true">+</span></summary>
                <p>{a}</p>
              </details>
            ))}
          </div>
        </section>

        <section className="ld-cta-wrap" aria-labelledby="cta">
          <div className="ld-cta">
            <h2 id="cta">Ready before your registration date.</h2>
            <p>It takes about five minutes. Bring your DPR.</p>
            <button className="ld-btn ld-btn-white" onClick={start}>
              Start planning <Icon name="arrow" size={18} />
            </button>
          </div>
        </section>
      </main>
      <footer className="ld-footer">
        <div>
          <span className="ld-foot-logo">Gator<span>Path</span></span>
          <nav aria-label="Footer">
            {LINKS.map(([id, label]) => (
              <a href={`#${id}`} key={id}>{label}</a>
            ))}
            <a href={NAVIGATOR} target="_blank" rel="noreferrer">Talk to an advisor</a>
          </nav>
          <p>Unofficial student-built tool, not affiliated with SF State. Your DPR and an advisor have the final word.</p>
        </div>
      </footer>
    </>
  );
}
