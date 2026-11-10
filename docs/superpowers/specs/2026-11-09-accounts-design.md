# Accounts: sign in with a student email, and keep the plan (design)

Status: draft for the owner's approval. Nothing is built. Calls the author made are marked **(my call)**; the owner
decides the ones under "Needs the owner".

## Why

Today a student's record, goals and plan live in the tab's session storage (ARCHITECTURE §9). Closing the tab loses
them, and a plan can't follow a student from a laptop to a phone. The owner wants sign-in with a student email and a
database that keeps the plan. This reverses golden rule 5 ("no student data at rest") for the website, so it comes
with a written exception, a privacy page and a way to delete everything.

## Goals

1. A student signs in with an SF State email and gets their plan back on any device.
2. Only student emails can sign up (`mail.sfsu.edu`). Staff and other addresses can't.
3. Signing in is optional. Everything that works today without an account keeps working.
4. A student can see what's kept, download it, and delete it, in two clicks each.
5. Keep as little as possible: the plan and the answers that make it, nothing else.

## Non-goals

- Passwords, social login, or non-school emails.
- Several saved plans per student, sharing a plan, or an advisor looking at a student's plan.
- Accounts for the MCP server. `server.py` and `engine/` stay stateless and never import the account code (golden
  rules 4 and 5 hold there; a test checks the import, as it does for `assistant.py`).
- Sending reminders or any email other than the sign-in code.
- Storing the DPR PDF, the transcript PDF, a name, an ID number, or the GPA.

## Anti-goals (a failure even if it works)

- A student is forced to sign in to plan.
- The database holds more than the student can see on their "What's kept" screen.
- A breach would reveal grades in a form that a copied database file reads in plain text, with no way for a student to
  have deleted it.
- The landing page or footer still says "nothing is saved" while it is.

## What the student sees (screens in text)

**Landing and header.** A "Sign in" link beside "Start planning". Signed in with a saved plan, the main button reads
"Continue your plan". Signed in with none, it reads "Start planning" as today.

**Sign-in (a card over the page, two steps).**
1. "Sign in with your student email." One field, "you@mail.sfsu.edu", button "Email me a code".
   Any other address: "GatorPath is for SF State students. Use your student email (@mail.sfsu.edu)." Same screen creates the account:
   there is no separate sign-up.
2. "We sent a 6-digit code to a\*\*\*@mail.sfsu.edu. It works for 10 minutes." One field, "Sign in", "Send a new code",
   "Use a different email". Wrong code: "That code didn't work" (and a count of tries left after the third miss).

The first message never says whether the address already had an account.

**While planning, signed in.** A quiet line in the workspace header: "Saved to your account · just now", or "Saving…",
or "Not saved: you're offline. We'll try again." The header menu has "Your account".

**Your account.** What's kept, in words: "Your courses and grades from your DPR, your goals, and your plan. Not your PDF,
name, ID or GPA." Buttons: "Download my data" (one file), "Sign out", "Delete my account and data" (asks once,
says it can't be undone, deletes at once).

**First sign-in with work in the tab.** "You have a plan in this tab. Save it to your account?" If the account already
has a plan: "Keep the plan in this tab or the one in your account?" with each one's date. The one not kept is dropped.

**Signed out or session ended mid-plan.** The tab's own copy keeps working exactly as today. The save line says
"Sign in to keep this plan."

## How it works

### Sign-in with an emailed code **(my call: over Google sign-in)**

A code works for any school address without depending on which sign-in SF State uses, and needs no password to store.
Google sign-in limited to the school's domain would be less typing but ties the site to a provider setup the owner
would have to confirm; it can be added later beside this.

- Allowed domain: `mail.sfsu.edu` only, decided by the owner 2026-11-09; **to confirm** with a real student address
  before launch. A setting, not hard-coded, so a second domain is one line.
- `POST /api/auth/code {email}`: lowercase and trim the address, check the domain, then always answer 200 with the
  same text. If allowed, make a 6-digit code from `secrets`, store its SHA-256 hash with the address and an expiry (10
  minutes), and email it. Sending is limited to 3 per address per hour and 10 per network address per hour, and a new
  code replaces the old one.
- `POST /api/auth/verify {email, code}`: compare with `hmac.compare_digest`; 5 wrong tries kill that code; a used code
  is deleted. On success, find or create the account, and start a session.
- Session: 32 random bytes from `secrets`; only its SHA-256 is stored. It reaches the browser in a cookie named
  `gp_session`: `HttpOnly`, `Secure` (off only on 127.0.0.1), `SameSite=Lax`, 30 days, renewed when used. Signing
  out deletes the row. Changing state requires a custom header (`X-GatorPath: 1`) so a form on another site can't send it.
- No access log of addresses; the code and session tables hold hashes, not the secrets.

### The database **(my call: SQLite, the standard library's `sqlite3`)**

`data/accounts.db`, separate from `catalog.db`, on a disk that survives restarts. One server process, so SQLite's one
writer is enough for a school's worth of students; move to Postgres only if the site needs more than one server. No new
dependency.

| Table | Columns |
|---|---|
| `accounts` | `id`, `email` (unique, lowercase), `created`, `last_seen` |
| `codes` | `email`, `code_hash`, `expires`, `tries` |
| `sessions` | `token_hash`, `account_id`, `expires`, `last_used` |
| `plans` | `account_id` (unique), `saved` (JSON), `updated` |

`plans.saved` holds the same record the tab saves now (`SavedSession` in `App.tsx`): profile, the imported course rows,
the built plan and the workspace state. **Dropped before saving:** the chat transcript and the Undo copy (free text
the student typed, and size), `sf_state_gpa`, and the DPR's notes. **(my call.)** The page checks the shape on load
exactly as `savedSession()` does today, so a bad row means "start over", not a crash.

Encryption at rest is the host's disk encryption, not application encryption. **(my call; the upgrade is a key kept
outside the database.)**

### Saving **(my call: one plan, last write wins)**

`GET /api/saved` returns the plan and its `updated` time, or `null`. `PUT /api/saved` replaces it (about 1 MB at most).
`DELETE /api/saved` and `DELETE /api/account` remove the plan, or the account and everything under it, in one
transaction. `GET /api/account/export` returns the plan as a file. The page saves 2 seconds after the last change, as
it does to session storage today, and also saves to session storage so a dropped connection loses nothing. If the
server's `updated` is newer than the page's last-known time, the page asks which to keep instead of overwriting.

### What stays as it is

Planning, auditing, the DPR import and the chat all work signed out. The DPR PDF is still read in memory and never
saved. Gator AI still sees only what it sees now. The AI helper's limits stay per network address in v1 **(my call;
per-account limits would be fairer on a campus network, and signing in makes them possible later)**.

## Rule and copy changes

- ARCHITECTURE: a new decision (D37) and an exception in §9 and §7.6: "The website, only when a student signs in, keeps
  their plan in `accounts.db` until they delete it or 12 months pass without a sign-in." The MCP server is unchanged.
  The line in §7.6 "no database and sets no cookies" becomes true only for signed-out use.
- AGENTS.md golden rule 5 gets that same one exception, beside the two it already has.
- Copy to change together: the landing's "Is my data safe?" answer and "Your DPR PDF is never saved", the `PRIVACY`
  text in `ui.tsx`, the footer's "Clear my saved data" (it clears the tab's copy; the account has its own delete), and
  the tests that pin these sentences.
- A short privacy page, linked from the sign-in card: what is kept, why, who can read it (the owner, as the person who
  runs the server), how to delete it, and that GatorPath is not SF State's.

## Constraints

- Python stdlib first: `smtplib`, `sqlite3`, `secrets`, `hmac`, `hashlib`. No new dependency without the owner's yes.
- `api.py` stays thin routes. The account code goes in its own module (`accounts.py`), imported only by `api.py`.
- Every rule in `engine/` is untouched. `check_plan` is untouched.
- Tests: the auth rules (domain, expiry, tries, rate limits, one code at a time, no "this email exists" leak, cookie
  flags), a signed-out run of every existing route, a saved plan that fails its shape check, delete leaves nothing,
  and the import check that `server.py` and `engine/` never reach `accounts`.
- Test mail goes to a function the tests replace, never to a real address; with no mail settings, local development
  prints the code to the terminal.

## Needs the owner

1. **Where it runs.** Accounts need a server online all the time, with a disk that survives restarts, HTTPS and a
   domain. Today nothing is deployed; `uv run gatorpath-web` runs on the owner's machine. Which host, and what monthly
   cost is acceptable on top of the $20 AI budget? (Fly.io, Render and a small VPS all do this for a few dollars.)
2. **Who sends the code.** Delivery needs mail that lands in an inbox: either an SMTP account on a domain the owner
   controls (with its SPF/DKIM records set), or a mail service such as Resend, which is a new dependency and account
   to approve. Which?
3. **How long to keep a plan.** 12 months after the last sign-in, then deleted automatically **(my call)**. Shorter or
   longer?
4. **Whose problem a breach is.** The database holds real grades. The owner should decide whether that is acceptable
   for a student-built site, and whether to tell SF State before launch. The author can't answer this and isn't a
   lawyer.

## Left to the builder

Table indexes and migrations (one `schema.sql` run at startup is enough), the card's exact wording and styling in the
existing design language, the mail template, how the save line behaves on a slow connection, and the cleanup job that
deletes expired codes, sessions and plans (it can run at startup and once a day).

## Order of work

1. Decide 1 and 2 above, so there is somewhere to run and a way to send.
2. `accounts.py` and its tests: codes, sessions, the four tables.
3. The routes, signed-out behavior unchanged, the import guard test.
4. The sign-in card, the account menu and the save line.
5. Rule, copy and privacy page changes, with the tests that pin them.
6. Deploy behind the chosen host and send a real code to a real school address before anyone else uses it.
