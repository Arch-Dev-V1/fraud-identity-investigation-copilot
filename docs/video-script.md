# Demo video — what to say

Written to be spoken, not read. Short sentences on purpose. Say it in your own
words; these are the beats, not a teleprompter.

Straight through, this runs **about 6 minutes**.

---

## Before you hit record

```bash
./run.sh
```

- [ ] Sidebar shows **Live mode** and **Transport: `mcp`**. If it says "gateway not running", the stack isn't fully up.
- [ ] Demo mode toggle is **off**.
- [ ] Marcus Hoyt is selected (he's top of the list by default) and the chat is empty. Hit **Clear chat** if not.
- [ ] One run costs about **$0.38** and takes roughly 30–90 seconds. Budget for two, in case the first stalls.
- [ ] Browser at 100% zoom, window wide enough that both panels show without scrolling.

---

## 1. What this is, and what's different (~75s)

> This is a fraud investigation copilot. The problem it works on is synthetic identity fraud.
>
> That's where someone invents a person who doesn't exist. They take a real Social Security number, pair it with a made-up name and date of birth, and then patiently build that identity a credit history — two or three years of small accounts, paid on time — before borrowing as much as they can and disappearing.
>
> It's hard to catch because by the time they borrow, the file looks completely normal.
>
> So a scoring service flags an application. This tool picks it up, investigates it, and writes a case memo for a human analyst.

**The three differentiators are the point of the whole video. Don't rush them.**

> Three things make this different from a typical AI demo.
>
> **First, it argues against itself.** Every memo has to include the case *for* the applicant, not just against. Most flagged applications aren't fraud. A tool that only ever argues one way quietly pushes analysts into declining real people.
>
> **Second, it can't make the decision.** Not because I told it not to in a prompt. Because there's no approve, reject or escalate tool for it to call. It physically cannot. The only thing in this system that writes a decision is the analyst's button.
>
> **Third, no vector database, no RAG.** Every lookup is an exact structured query against real-shaped data. That's how fraud tooling actually works.
>
> And everything you're about to see is fabricated data, built for this demo.

---

## 2. The two panels (~60s)

**Point at the left.**

> Two panels. On the left is the conversation. It works the way you'd expect an agent to — a transcript, and a box at the bottom where I can type.
>
> Two buttons. **Run investigation** hands the whole case over. **Send** is just an ordinary question, if I want to ask it something.

**Point at the right.**

> On the right is the work queue. Fifty flagged applications, worst score first. Red is high risk.
>
> This one at the top — Marcus Hoyt — scores 918 out of 999.
>
> Underneath is the snapshot for whichever case I've selected. The composite score, and then it's split two ways. **First-party** means a real person misusing their own credit. **Third-party** means a stolen or invented identity. Here third-party is 935 and first-party is 640 — so the provider is pointing at a fake identity, not a real person gone bad.
>
> Then the reason codes. Those are the four things that tripped the flag.
>
> And at the bottom — the decision buttons aren't there yet. It just says "available once a case memo has been submitted."

**Optional, 10 seconds, sidebar:**

> There's also a demo mode that runs the whole thing with no model call at all. That's how I built the interface without spending anything. It's off right now — this is a live run.

---

## 3. Starting it (~25s)

**Click the case, then pause on the composer before you click Run.**

> I'll take the top one.
>
> When I click a case, it drops the case brief straight into the message box. So this is exactly what the agent is about to be told — name, date of birth, SSN, address, the score, the reason codes. I could edit this, or add a question to it. I'll send it as it is.
>
> Run investigation.

---

## 4. While it runs (~75s of filler — rehearse this one)

**Narrate the status feed. Name each tool out loud as it appears.**

> While that runs, here's what's happening underneath.
>
> The brief went to the model along with four lookup tools it's allowed to call. What it did *not* get is a script. There's no fixed checklist saying check the SSN first, then credit, then links. It decides what to look at based on what's actually wrong with this case.
>
> There — it's called `check_ssn_verification`.

**As the others appear:**

> `check_credit_trajectory` — that's the credit file.
>
> `check_shared_identifiers` — that's asking who else shares this person's phone, address, device or IP address.

**Then the layers:**

> Every one of those calls goes through four layers.
>
> First, the agent checks the request is for the right applicant. If the model ever asked about somebody else, it gets refused right there.
>
> Then it goes out over MCP — a standard protocol for exposing tools — to a mock vendor gateway. That's an HTTP service standing in for the real fraud APIs a lender would buy. It reads the database and answers the way a vendor would.
>
> That layering isn't decoration. It means swapping in a real provider is a change inside one function, not a rewrite.
>
> And every call is being written to an audit log as it happens — what was asked, what came back, when. That's what lets someone six months later see why the memo said what it said.

**Spare paragraph if it's still running:**

> One thing worth noticing — it isn't calling all four tools every time. It calls one, reads the answer, then decides whether it needs another.

---

## 5. The results (~90s)

**Scroll to the top of the memo.**

> Right. Done.
>
> The memo comes back in the conversation, as the agent's reply.
>
> Top line — **confidence: high**. Not "this is fraud". A confidence level. And underneath it says advisory only, no disposition has been made.

**Scroll to the timeline.**

> Then the maturation timeline. This is the reconstruction — how this identity got built, in order. The SSN first shows up in credit records in August 2016. Then in 2022 he's added to someone else's credit card as an authorized user, which hands him that account's age without him ever having repaid anything. Then four accounts of his own in under three years.

**Scroll to evidence.**

> Then the evidence. And look — every finding is tagged with the lookup that produced it. That's not cosmetic. It means nothing in here is asserted without a tool call behind it.
>
> The strongest two. Social Security *confirms* the number, name and date of birth go together — it passes that check. But the number has no credit record at all before 2016, and the claimed birth year is 1991. A real 1991 identity leaves about 25 years of records.
>
> And the same device and IP address show up on two other flagged applications. All three inside eleven days.

**Scroll to the counter-narrative. Slow down here.**

> And then this section. The counter-narrative. This is the agent arguing the other side.
>
> It goes signal by signal and gives the innocent explanation for each one — an SSN with no history also fits someone who immigrated as an adult; an authorized-user card is also how a parent helps a teenager build credit — and then says what evidence would actually settle it.
>
> On this case it concedes that's a weak argument, and says why. On a different case it wouldn't be.

**Expand the two sections.**

> Underneath, two things. **Investigation steps** — every tool call in order. And the **tool-call trail**, which is the actual audit record that got written, with the token usage for the run.

**Point at the decision buttons.**

> And now the decision buttons have appeared. The agent has made no decision — that field is still empty in the database. It stays empty until I click one.

---

## 6. What makes it agentic (~75s — close on this)

> Last thing. What actually makes this agentic, rather than just a clever prompt.
>
> **One — it chooses its own tools, and its own order.** I didn't write a pipeline. A case flagged for a shared device gets a different investigation from one flagged for sudden borrowing.
>
> **Two — it decides when to stop.** The loop doesn't run a fixed number of times. After each result it decides whether it has enough or needs more. That exit condition belongs to the model, not to me.
>
> **Three — results change its next move.** It isn't one prompt and one answer. What comes back from a lookup feeds the next decision.
>
> **Four, and this is the one I'd argue matters most — it's bounded on purpose.** An agent that can do anything isn't ready for production. This one has four lookups and one memo it can write. That's the whole surface.
>
> And the things it deliberately *can't* do — decide a case, look up a different applicant, write to the audit log from outside the agent — those aren't instructions in a prompt that it might ignore on a bad day. They don't exist as capabilities at all.
>
> Which, for anything touching a lending decision, is the part that matters.

---

## If something goes wrong on camera

| What happens | What to say |
| --- | --- |
| Run is slow (over 90s) | "It's working through the lookups — it decides how many it needs, so this varies by case." Then use the spare paragraph from section 4. |
| Sidebar says "gateway not running" | Don't hide it. "The gateway isn't up, so it's falling back to in-process lookups — and it tells you that, rather than failing quietly." That's a feature. Say it as one. |
| A tool result shows an error | Read the message first. If it's the scope guard: "That's the guard refusing a lookup that wasn't for this applicant." |
| The memo looks thin | Say so. "That's a weaker memo than usual — which is exactly why there's a 50-case test set in the project, rather than me judging it by eye." |

---

## Extras, if you want a longer cut

- **Run Nadia Osei-Kwame (538) as a second case.** She's the strongest proof of the counter-narrative point. No US credit record before 2021 against a 1986 birth year, which looks damning — but she moved to the US as an adult. The agent should land on **low**. Showing the tool decline to cry fraud is more persuasive than showing it catch one.
- **Show the gateway terminal** running with `PROVIDER_API_TRACE=body ./run.sh` — the real HTTP responses scroll past as the agent works.
- **Open the scoring report** at `.claude/hillclimb/investigation/report.html`, if you've run the eval.
- **Mention cost.** One investigation is about 38 cents, measured. Roughly 83% of that is the model's own reasoning, not the memo — which is why the next change is turning the reasoning effort down and measuring whether quality holds.
