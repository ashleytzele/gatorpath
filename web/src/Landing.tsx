import { useState } from "react";
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

const ROUTE = [
  { term: "Fall 2026", tag: "In progress", state: "now", courses: "CSC 220 · CSC 230 · ENG 114" },
  { term: "Spring 2027", tag: "Register next", state: "next", courses: "CSC 256 · MATH 227 · PHYS 230" },
  { term: "Fall 2027", tag: "", state: "later", courses: "CSC 340 · MATH 225 · CSC 300GW" },
  { term: "Spring 2029", tag: "Graduate", state: "next", courses: "CSC 648 · two electives" },
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
  ["Is my data safe?", "Your DPR is read in memory and never stored. The AI helper sees your major, goal and courses, never your name, ID, grades or GPA. It only learns a grade if you type one in the chat."],
  ["What’s a DPR, and how do I get it?", "Your Degree Progress Report shows your completed courses and what your degree still requires. In Student Center, open Degree Progress Report, click Expand All and View All, then Print → Save as PDF."],
  ["Does it work for my major?", "It has the 2026–27 rules for the bachelor’s programs listed when you choose your goals, written from the Bulletin. Always compare your plan with your DPR and an advisor."],
  ["Does it use AI?", "Only to choose electives and to answer in the chat (Claude Haiku). Planning and every check are rules from the Bulletin, not AI. The chat has a daily limit; planning works without it."],
];

export function Landing({ start }: { start: () => void }) {
  const [played, setPlayed] = useState(false);
  return (
    <>
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
      <main id="top" className="ld">
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
          <p className="ld-fine">No account needed. Your DPR is never stored.</p>
        </section>

        <section id="demo" className="ld-demo" aria-label="Demo video">
          <div className="ld-frame">
            <div className={`ld-poster ${played ? "blur" : ""}`} aria-hidden="true">
              <div className="ld-poster-plan">
                <p className="ld-poster-title">You can graduate <span>Spring 2029</span></p>
                <div className="ld-poster-route">
                  <p className="dot on"><b>Spring 2027</b> <span>· Register next</span></p>
                  <p className="sub">CSC 256 Machine Structures · MATH 227 Calculus II</p>
                  <p className="dot off"><b>Fall 2027</b></p>
                  <p className="sub">CSC 340 Programming Methodology · MATH 324</p>
                  <p className="dot on"><b>Spring 2029</b> <span>· Graduate</span></p>
                </div>
              </div>
              <div className="ld-poster-chat">
                <p className="ask">Can I finish sooner?</p>
                <div className="reply">
                  <p className="who">GatorPath</p>
                  <p>Yes: with summer terms you’d graduate Fall 2028.</p>
                </div>
                <p className="note"><b>✓ Plan updated</b> · checked against the Bulletin</p>
              </div>
            </div>
            <button type="button" className="ld-play" aria-label="Play the 1-minute demo" onClick={() => setPlayed(true)}>
              <span aria-hidden="true" />
            </button>
            {played && <p role="status" className="ld-soon">The demo video is coming soon.</p>}
          </div>
          <p className="ld-caption">Demo video coming soon · about a minute, with a made-up student</p>
        </section>

        <section className="ld-facts" aria-label="About GatorPath">
          <ul>
            <li>✓ Built from the 2026–27 SF State Bulletin</li>
            {/* the count is the number of rules/programs/2026-27/*.yaml; tests/test_api.py compares it */}
            <li>✓ Rules for 108 majors</li>
            <li>✓ Every plan checked</li>
            <li>✓ Your DPR is never stored</li>
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
        </section>

        <section className="ld-band" aria-labelledby="route">
          <div className="ld-split ld-sec">
            <div className="ld-route-box" aria-hidden="true">
              <div className="ld-route">
                {ROUTE.map((r) => (
                  <div className={`stop ${r.state}`} key={r.term}>
                    <i />
                    <p><b>{r.term}</b> {r.tag && <span>· {r.tag}</span>}</p>
                    <p className="c">{r.courses}</p>
                  </div>
                ))}
              </div>
            </div>
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
