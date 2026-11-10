import { Icon, Logo, NAVIGATOR } from "./ui";

const LINKS = [
  ["how", "How it works"],
  ["what", "What you get"],
  ["questions", "Questions"],
] as const;

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
  ["Is GatorPath official?", "No. GatorPath is a student-built planning aid. Your DPR is the official record, and your academic advisor confirms what counts toward your degree."],
  ["Is my data safe?", "Your DPR PDF is read in memory and never saved. Your record and plan stay in this browser tab's session storage so a reload keeps your work; they clear when you close the tab or choose Clear my saved data. Gator AI sees your major, goal and courses, never your name, ID, grades or GPA. It only learns a grade if you type one in the chat."],
  ["What’s a DPR, and how do I get it?", "Your Degree Progress Report shows your completed courses and what your degree still requires. In Student Center, open Degree Progress Report, click Expand All and View All, then Print → Save as PDF."],
  ["Does it work for my major?", "It has the 2026–27 rules for the bachelor’s programs listed when you choose your goals, written from the Bulletin. Always compare your plan with your DPR and an advisor."],
  ["Does it use AI?", "Gator AI chooses electives and answers in the chat (Claude Haiku). Planning and every check use Bulletin rules. Gator AI has hourly and daily limits; planning works without it."],
];

// the buttons the chat really offers under a plan
const ASKS = ["Choose my open courses", "Finish sooner", "Lighter terms", "Add summer", "Add Winter Session", "Compare with another major"];

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
        <section className="lp-hero">
          <div className="lp-hero-copy">
            <p className="ld-label">For SF State students</p>
            <h1>Plan your path to graduation in 5 minutes.</h1>
            <p className="lp-lede">
              Upload your DPR, tell us your goals, and get a semester-by-semester plan checked against
              the Bulletin, plus next term’s schedule with no time clashes.
            </p>
            <div className="lp-actions">
              <button className="ld-btn ld-btn-green" onClick={start}>
                Start planning <Icon name="arrow" size={18} />
              </button>
            </div>
            <p className="ld-fine">No account needed. Your DPR PDF is never saved.</p>
          </div>
          <figure className="lp-demo">
            {/* plays by itself, silent and on repeat, with controls to pause it (WCAG 2.2.2); a student who asks for less motion gets a still poster */}
            <video className="lp-demo-video" controls muted playsInline preload="metadata" poster="/landing-upload.jpg" aria-label="GatorPath walkthrough from picking a major to a plan"
              {...(window.matchMedia("(prefers-reduced-motion: reduce)").matches ? {} : { autoPlay: true, loop: true })}>
              <source src="/gatorpath-demo.mp4" type="video/mp4" />
              Your browser can’t play this video. You can still start planning below.
            </video>
            <figcaption>A short walkthrough with a fictional new student, from picking a major to a checked plan.</figcaption>
          </figure>
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

        <section id="how" className="lp-sec" aria-labelledby="howh">
          <h2 id="howh">Three steps, about five minutes.</h2>
          <ol className="lp-steps">
            {STEPS.map(([title, text], i) => (
              <li key={title}>
                <span className="lp-step-dot" aria-hidden="true">{i + 1}</span>
                <h3>{title}</h3>
                <p>{text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="what" className="lp-sec lp-sec-top" aria-labelledby="whath">
          <h2 id="whath">Everything your DPR leaves you to work out.</h2>
          <p className="ld-sub">Your DPR tells you what’s done. GatorPath works out what to take, and when.</p>
          <div className="lp-row">
            <div className="lp-copy">
              <h3>Your record, read for you</h3>
              <p>Upload your DPR and see every requirement, course, grade and unit on one clear page. Open any section to check it.</p>
              <ul className="lp-ticks">
                <li>Complete, in progress, planned and still needed, counted separately</li>
                <li>Fix anything the DPR got wrong before you plan</li>
              </ul>
            </div>
            <figure className="lp-shot">
              <img src="/landing-requirements.jpg" width="1400" height="694" alt="The Requirements page: General Education, SF State Studies, American Institutions, University requirements and Major, each with how many requirements are complete, planned and still needed" loading="lazy" />
            </figure>
          </div>
        </section>

        <section className="lp-route" aria-labelledby="route">
          <div className="lp-route-inner">
            <figure className="lp-shot lp-shot-light">
              <img src="/landing-route.jpg" width="1500" height="716" alt="A term-by-term plan: Spring 2027, 16 units, with each course, its units and the requirement it counts for" loading="lazy" />
              <figcaption>Sample plan for a fictional student</figcaption>
            </figure>
            <div className="lp-copy">
              <h2 id="route">See your whole route.</h2>
              <p className="lp-route-sub">Every term to graduation on one page, and the reason each class sits where it does.</p>
              <ul className="lp-points">
                {POINTS.map(([lead, text]) => (
                  <li key={lead}><b>{lead}</b> {text}</li>
                ))}
              </ul>
              <button className="ld-btn ld-btn-white" onClick={start}>Start planning</button>
            </div>
          </div>
        </section>

        <section className="lp-sec" aria-label="Ask and schedule">
          <div className="lp-row lp-row-chat">
            <figure className="lp-chat">
              <img src="/landing-chat.jpg" width="700" height="1146" alt="The Gator AI chat after a plan is built: it says what it filled, what changed and what to check, then shows a checked change" loading="lazy" />
            </figure>
            <div className="lp-copy">
              <h3>Ask, and it changes</h3>
              <p>Finish sooner, lighter terms, a different GE: ask the chat. Every change is checked against the Bulletin again before it lands, and you can undo it.</p>
              <p className="lp-asks-lead">Under your plan, one press does it:</p>
              <ul className="lp-asks">
                {ASKS.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
          </div>

          <div className="lp-row lp-row-spaced">
            <div className="lp-copy">
              <h3>Next term’s schedule</h3>
              <p>Sections with no time clashes, with rooms, instructors and class numbers ready for registration.</p>
              <ul className="lp-ticks">
                <li>Choose another section and the rest fit around it</li>
                <li>Print it, with the right office for each question</li>
              </ul>
            </div>
            <figure className="lp-shot">
              <img src="/landing-schedule.jpg" width="1400" height="992" alt="A weekly class calendar, Monday to Friday, with each course's time, building and room" loading="lazy" />
              <figcaption>A sample week for a fictional student.</figcaption>
            </figure>
          </div>
        </section>

        <section className="ld-sec" aria-labelledby="limits">
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
          <p>Unofficial student-built tool, not affiliated with SF State. Your DPR and your academic advisor are the official sources for your degree requirements.</p>
        </div>
      </footer>
    </>
  );
}
