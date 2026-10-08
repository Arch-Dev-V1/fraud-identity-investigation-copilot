# Demo video — what to say

All the explaining happens **before** you click Run. After that you mostly point
at things. Spoken straight through: **about 4 minutes.**

---

## Before you record

```bash
./run.sh
```

- [ ] Sidebar reads **Live mode** and **Transport: `mcp`**
- [ ] Demo mode toggle **off**
- [ ] Marcus Hoyt selected (top of the list, already default), chat empty
- [ ] One run is ~**$0.38** and takes 30–90 seconds

---

## 1. Everything up front (~2 min 30)

**Screen just sits on the app. Don't click anything yet.**

> This is a fraud investigation copilot. The problem it works on is synthetic
> identity fraud — where someone invents a person who doesn't exist. A real
> Social Security number, a made-up name and date of birth. Then they spend two
> or three years quietly building that identity a credit history, before
> borrowing everything they can and disappearing.
>
> It's hard to catch, because by the time they borrow, the file looks completely
> normal.
>
> A scoring service flags the application. This picks it up, investigates it, and
> writes a case memo for a human analyst. Everything you'll see is fabricated
> data.

**Point right.**

> Right-hand side is the work queue. Fifty flagged applications, worst score
> first. Marcus Hoyt at the top — 918 out of 999.
>
> Below him, the snapshot. The composite score, split two ways: first-party means
> a real person misusing their own credit, third-party means a stolen or invented
> identity. His third-party is 935, so the provider is saying this person isn't
> real.
>
> Then the reason codes that tripped the flag. And the decision buttons, which
> aren't there yet.

**Point left.**

> Left is the conversation. **Run investigation** hands the case over. **Send** is
> just an ordinary question.

**Now the part that does the work. Slow down.**

> Three things make this different from a typical AI demo.
>
> **One — it argues against itself.** Every memo has to include the case *for* the
> applicant. Most flagged applications aren't fraud, and a tool that only argues
> one way pushes analysts into declining real people.
>
> **Two — it can't decide.** Not a prompt rule. There's no approve or reject tool
> for it to call. The only thing in the system that writes a decision is my
> button.
>
> **Three — no vector database, no RAG.** Every lookup is an exact structured
> query, which is how fraud tooling actually works.

**Then, still before clicking:**

> And here's exactly what happens when I click.
>
> The case brief goes to the model along with four lookup tools — and no script.
> No fixed order. It picks what to check based on what's wrong with this case.
>
> Each call it makes gets checked that it's for the right applicant, then goes out
> over MCP to a mock vendor gateway — an HTTP service standing in for the real
> fraud APIs a lender would buy — which reads the database. Every call lands in an
> audit log as it happens.
>
> It keeps going until it decides it has enough, then writes the memo.
>
> So what you're about to watch is it choosing, reading, and choosing again.

---

## 2. Click it, then stop talking (~15s of words)

> Running it now.

**Then be quiet and let the feed scroll. Only if you want to fill:**

> — SSN check. Credit file. Shared identifiers.

**Only if it's slow:**

> It decides how many lookups it needs, so this varies by case.

---

## 3. The memo (~50s)

**Point as you scroll. Short lines.**

> Confidence: **high**. Not a verdict — a confidence level. And it says advisory
> only, no disposition made.
>
> The timeline is the reconstruction. SSN first appears in credit records in 2016.
> Added to someone else's card in 2022, which hands him that account's age for
> free. Then four accounts of his own in under three years.
>
> Every piece of evidence is tagged with the lookup that produced it. Nothing in
> here is asserted without a tool call behind it.
>
> The two strongest. Social Security *confirms* the number, name and date of birth
> go together — it passes. But no credit record at all before 2016, against a 1991
> birth year. And the same device and IP address on two other flagged
> applications, all three inside eleven days.

**Stop on the counter-narrative.**

> And this is the part I'd point at. The counter-narrative — the agent arguing the
> other side, signal by signal, and saying what evidence would settle it.

**Expanders, then the buttons.**

> Every step and the full audit record are underneath.
>
> And now the decision buttons exist. That field is still empty in the database.
> It stays empty until I click one.

---

## 4. Why it's agentic (~30s)

> Four things make this agentic rather than a clever prompt.
>
> It picks its own tools and its own order. It decides when to stop. Each result
> changes its next move.
>
> And it's bounded on purpose. Four lookups, one memo — that's the whole surface.
> The things it can't do — decide a case, look up a different applicant — aren't
> prompt rules it might ignore on a bad day. They don't exist as capabilities.
>
> Which, for anything touching a lending decision, is the part that matters.

---

## If something goes wrong

| What happens | What to say |
| --- | --- |
| Run is slow | "It decides how many lookups it needs, so this varies by case." |
| "gateway not running" | "It's fallen back to in-process lookups — and it tells you, rather than failing quietly." Present it as a feature. |
| Memo looks thin | "Weaker than usual — which is why there's a 50-case test set in the project rather than me judging by eye." |

---

## If you want a longer cut

- **Run Nadia Osei-Kwame (538) second.** No US credit record before 2021 against a
  1986 birth year — looks damning, but she moved to the US as an adult. The agent
  should say **low**. Showing it decline to cry fraud is more persuasive than
  showing it catch one.
- **Cost:** about 38 cents per investigation, measured. Roughly 83% of that is the
  model's own reasoning, not the memo.
