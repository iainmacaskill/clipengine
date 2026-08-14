# Follow-up session — Nadean & Richard: problem sign-off

**Purpose:** Step through the six draft problem statements from pass 1, in three stages, in this order:
1. **Definition** — agree each problem is real and worded right, in their words. Nothing advances until it's agreed.
2. **Priority** — rank only the agreed problems.
3. **Cost & impact** — quantify only the top-ranked ones.

**Ground rules for the session (say these up front):**
- "Today is still about the problems, not fixes. If we drift into solutions — including the QA workflow you've already built — I'll park it and pull us back."
- "Where I quote you, tell me if the transcript caught you wrong. I'd rather rewrite a statement than sign off a misquote."
- "Where a number was uncertain last time, I'll ask who can pull the real figure rather than settle for a guess."
- Record the session (they were comfortable being recorded last time).

**Facilitation notes:**
- Ask the open question first; only use the probes if it doesn't come out naturally.
- Nadean and Richard disagreed on at least one point last time (see PS2). Get an answer from each of them separately where marked **[both]** — a split view is a finding, not a failure.
- Cross-references (P1, T3, etc.) point to `discovery-pass-1-customer-success.md`.

---

## If the session runs short: the core ten

1. "Reading the six statements as written — which would you change, and which would you strike?" **[both]**
2. "Which single problem, left unfixed for a year, hurts retention most?" **[both]**
3. "Is the QA problem the *coverage* (120 of ~1,700+ calls a month), the *consistency* (different listeners score differently), or the *credibility* (feedback gets dismissed)? If you could only fix one, which?"
4. "What decision would a team leader make differently if they could see a CSM's last 50 calls instead of 8?"
5. "On the sales handover: if you had full access to every sales call recording tomorrow, but the handover meeting stayed as it is — is the problem solved?"
6. "Is it 400 or 500 meetings a week — and who can pull the actual number?"
7. "The one-third no-show figure was 'we've heard'. Who can pull the real attended-vs-booked rate before we sign this off?"
8. "How many of your 5,000 customers sit in the disengaged pot today?"
9. "What is the GRR number and its three-year trend? I can't cost any of these problems without it."
10. "Which of these six problems is genuinely yours to own, and which belong to sales, product, or support?"

---

## Stage 1 — Problem definition

Take the six draft statements one at a time. For each: read it aloud, then ask the **confirm** question, then probe. Capture the rewording in their words on the spot.

### PS1 — "We quality-check almost none of our customer calls…" (P1, P2, P3)

**Confirm:** "Is that true as written? What would you change?"

**Probes:**
- "This statement bundles three things: coverage (one person, 120/month), consistency (you told me 'it's how different people interpret the call'), and credibility ('oh, I think that was a one-off'). Are those one problem or three?" **[both]**
- "If every call were checked tomorrow but nothing else changed, what would still be broken?" *(Separates coverage from credibility without proposing anything.)*
- "How does the monthly nomination list — 'based on their tenure or risk' — shape who never gets QA'd? Is the sampling itself part of the problem?"
- "Richard, you said team leaders say 'that was a one-off'. What happens after that? Does the feedback die there?"
- "When Jack, Nadean and a team leader score the same call differently — whose score stands today?"

**Watch for:** solution drift into the AI QA build. Park it: "That's the fix — we'll assess it in the next pass. Today I need the problem agreed."

### PS2 — "We cannot see how any CSM performs across their recent calls as a whole…" (P4, P5)

**Confirm:** "Is the problem 'we can't see across calls', or is it really 'team leaders coach without evidence'? Which wording is yours?"

**Probes:**
- "What decision would you or a team leader make differently with a 50-call view that you can't make with an 8-call view?"
- "Why 50 calls? Where did that number come from — is it a month's work, a judgment call, something else?"
- "Nadean — Kayla flagged calls as 'completely off' the day before we spoke. Richard — you felt consistency was 'pretty much nailed'. I want to state this fairly: how confident is each of you, today, that a team leader reading a score can trust it?" **[both]** *(Resolves T3 — this decides whether score trust is part of the problem statement or not.)*
- "Is the trust question a separate problem from the aggregation question, or the same one?"
- "Nadean, how much of your week currently goes on checking the scores yourself?" *(Definition now, quantified in Stage 3.)*

**Watch for:** this problem lives inside their in-flight build. Keep the statement about the *missing capability and its consequence*, not about PlanHat or models.

### PS3 — "What the sales team learns about a customer largely fails to reach Customer Success…" (P7)

**Confirm:** "Is that fair, and is it worded the way you'd say it?"

**Probes:**
- "If you had full access to every sales call recording tomorrow, but the handover meeting stayed exactly as it is — solved, or not?" *(Separates the access problem from the behaviour/incentive problem: 'once sales have made the sale they don't care anymore… they get paid on renewals, so they should.')*
- "How often does wrong handover information surface *in front of the customer* — the ''your CRM is Salesforce' — 'no it's not'' moment? Weekly? Every onboarding?"
- "The official process has the salesperson joining the first onboarding call. Does that happen every time? When it does, does the problem still occur?" *(Resolves T4.)*
- "Is this a Customer Success problem statement, or a cross-department one? Can you sign it off alone, or does sales leadership need to agree it too — and if so, who?"
- "You mentioned someone in the US already turns Salesloft transcripts into handover docs, and Richard started to say 'we're not meant to use…'. What tooling are people allowed to use, and what's driving the workaround?" *(Skirted last time — raise it neutrally; the answer shapes how the problem is written, not any fix.)*

### PS4 — "CSM time is consumed by manual work around the calls themselves…" (P10, P11, P12)

**Confirm:** "This is the bundled one: call prep, data cleansing/portal setup, and no-shows wasting the prep. One problem about CSM time, or three problems?" **[both]**

**Probes:**
- "Last time the prep figure moved between 'a little bit more than a couple of hours' and 'five or more hours' per CSM per week. Which do you actually believe? Would you be comfortable time-sampling a normal week for a few CSMs before we lock the number?" *(Resolves T7.)*
- "The one-third no-show figure was 'we've heard'. Before this goes in a signed statement, who can pull the actual attended-vs-booked rate — from calendars, Jiminny, PlanHat?" *(Resolves T5.)*
- "Nadean, you said unprepped calls become 'a crap call and so on' — and separately that a bad last call is a reason customers skip the next one. Do you see those as one loop? Should the statement say so?"
- "On data cleansing: Richard, you routed this to Vicky — 'she might say we've got it pretty well covered.' Do we need Vicky's read before this bullet is signed, or are you confident it belongs?" *(Resolves T6.)*
- "Is giving the data work to new starters a problem, or deliberate training? You said 'once you've done it once, you don't really need to do it again' — so which is it?"
- "If a CSM got five hours a week back, what would they actually do with it — and would you be able to tell?" *(Their answer defines the cost of the problem in their terms; note it for Stage 3.)*

### PS5 — "We don't reliably know which customers need attention… and CSMs who hit every metric can still have poor retention" (P8, P9)

**Confirm:** "There are two claims in here: blind spots in coverage, and metrics that don't explain retention. Keep them together or split them?" **[both]**

**Probes:**
- "The 'twenty customers not spoken to for six months, in a really bad place' example — was that one CSM once, or a pattern? How was it discovered?" *(Their answer tells you how blind the blind spot really is.)*
- "'They're pretending everything's great' — how widespread do you believe that is? What would you accept as evidence either way?"
- "What does 'in a bad place' mean, precisely? If we can't define it, we can't count it — what signals would you list?"
- "For the CSMs who hit every metric with poor retention — how many are we talking about? Is that a couple of people or a cohort?"
- "You said 'there's no way for us to figure that out.' What have you already tried? What question, exactly, can you not answer today?" *(Keeps this as a problem definition, not a tool request.)*
- "Who owns this problem day-to-day — team leaders, the department heads, or the new data analyst?"

### PS6 — "Our customer records stay incomplete because the facts learned on calls don't get recorded…" (P6)

**Confirm:** "Fair and complete as written?"

**Probes:**
- "Which fields matter most? The CRM-in-use example ran two years unfilled — what's the list of facts you actually need per customer, in priority order?"
- "Can someone run a completeness report in PlanHat so the statement can say 'X% of customers have field Y blank' instead of anecdote? Who?"
- "Who is the consumer of this data? Is the pain today's (CSMs walking into calls not knowing the customer) or tomorrow's (the retention/ICP analysis being blocked)?" **[both]**
- "Why do you think it doesn't get recorded? Not to fix it today — but the statement should say whether this is a time problem, a tooling problem, or a 'nothing happens if I don't' problem, in your words."

### Definition stage close

- "Is there a problem we've missed that belongs on this list?" *(Explicitly re-offer the two they raised but we didn't elevate: the PTB/team-leader meeting quality question, and the customers-not-commercialising-the-data problem (P13) — "should either of these be a seventh statement, or do they belong to a different owner?")*
- "Last time Iain's notes said you'd had 'more issues' with the AI risk detection, but we never got to the issues. What were they — and is there a problem statement hiding there?" *(Skirted topic from pass 1.)*
- Read back the final agreed wording of every statement before moving on. "Are these, as now worded, your problems? Would Tom James recognise them?"

---

## Stage 2 — Priority

Only rank statements that survived Stage 1. Get independent answers first, then discuss.

1. "Rank them, one to N. No ties." **[both, separately — compare afterwards]**
2. "Which single problem, left unfixed for twelve months, does the most damage to retention?" *(Their stated number-one-and-number-two priority — use their frame.)*
3. "Which problem is most painful *daily*, even if it isn't the biggest? Sometimes those differ — do they here?"
4. "Nadean, you said you've 'got about six months to get quite a few projects done.' Which of these problems does that clock apply to, and who set it?"
5. "Which of these could you fix least easily without another department moving? Does that change its rank for a CS-owned effort?"
6. "If the two rankings differ: "Talk me through the difference — what does each of you see that the other doesn't?"
7. Close: "So the order we're agreeing is… — say it back, get explicit yes from both."

---

## Stage 3 — Cost & impact

Work down the agreed priority order; go as deep as time allows. For each problem: time, money, errors, customer experience, morale — and for every number, either a figure they'll stand behind or a named owner who can pull it.

### The numbers that must get resolved regardless of ranking

| # | Open number | Question | Likely owner |
|---|---|---|---|
| 1 | Meetings/week (400 vs 500 both said) | "Which is it? Can the data analyst pull actuals for last quarter?" | Richard / data analyst |
| 2 | No-show rate ("about a third", hearsay) | "Actual attended-vs-booked, by team, last quarter?" | Team leaders / data analyst |
| 3 | Prep hours ("couple" vs "five or more") | "Time-sample a normal week across a few CSMs?" | Nadean + team leaders |
| 4 | GRR figure and 3-year trend ("completely flat", no number) | "What's the number? Impact cases are impossible without it." | Richard / Tom James |
| 5 | Disengaged segment size ("this big part") | "How many of the 5,000?" | Nadean |
| 6 | PlanHat credit contract (1M vs 2M; month vs year; £20k vs £25k) | "Can you bring the contract, or name who holds it?" | Contract owner (unnamed) |
| 7 | Data-cleansing burden per onboarding | "Hours per new customer, and customers per month?" | Vicky |
| 8 | QA dispute rate ("often… a one-off") | "Of last month's QA feedback, how much was challenged?" | Team leaders / Nadean |

### Per-problem impact questions

**PS1 (QA coverage/credibility):**
- "What does Jack's QA cost — his time, fully loaded, per month?"
- "How many CSMs got zero QA'd calls last month?"
- "Can you point to a CSM whose performance didn't improve because feedback was dismissed? What did that cost — in their retention number?"

**PS2 (no cross-call view):**
- "Nadean — hours per week you personally spend validating scores?"
- "Team leader coaching sessions happen weekly per CSM — how much of that hour is spent arguing about evidence rather than coaching?"
- "What does the QA capability cost to run today — credits per call, against the contract?" *(Ties to open number 6.)*

**PS3 (handover):**
- "How many onboardings a month, and how much longer does onboarding run when the handover is bad — days? weeks?"
- "First-term churn: do customers with bad handovers cancel more? Could the data analyst test that?"
- "How many hours does a CSM spend reconstructing what sales already knew, per new customer?"

**PS4 (CSM manual load + no-shows):**
- "Take the agreed prep figure × 40 CSMs — do you accept that as the weekly cost, or is it 'if they're prepping properly' aspiration rather than actual?"
- "For no-shows: the cost you named was the prep plus the held hour, plus rearrangement. Anything else — morale? 'It's a very hard working role' — where does this land on that?"
- "Data cleansing: hours per new customer × onboardings per month — and whose hours (new starters vs experienced CSMs)?"

**PS5 (blind spots / metrics vs retention):**
- "Of the accounts that cancelled last quarter, how many had no meaningful contact in the prior six months? Can the data analyst pull it?"
- "What's the revenue in the disengaged segment?" *(Size from open number 5 × typical contract value — they quoted £3k contracts and 5,000 customers/£40M; use their figures only.)*
- "How many CSMs are in the 'hits all metrics, poor retention' cohort, and what's the retention gap between them and the best?"

**PS6 (CRM completeness):**
- "From the completeness report: which three fields are emptiest, and at what rate?"
- "What is the retention/ICP analysis worth if it works — and is missing data actually what's blocking the analyst today, or not yet?"

### Morale — deliberately underexplored in pass 1

- "We talked a lot about time and retention, almost nothing about how the team feels. Which of these problems do CSMs complain about? Which would team leaders say grinds them down?"
- "You said you've got 'some CSMs who are absolutely incredible hard workers' and 'a real range'. Do any of these problems widen that range?"

---

## Before closing

1. **Next interviews** — "For the problems you couldn't quantify or don't own alone, I'd like to speak to: Vicky (cleansing, cancellations), Jack (QA), Kayla (score quality), Ed and Michael (Salesloft/Cyclone), Mateo (expansion analysis), Brent (support tickets), Tom James (retention picture), the data analyst, and a couple of team leaders and CSMs. Who's missing, who's first, and will you make the introductions?"
2. **Data homework** — read back the owner-assigned numbers table; confirm who brings what by when.
3. **Sign-off mechanics** — "Once the reworded statements and the verified numbers are in, the document goes to you for a written yes. Who else has to sign — Tom James? Anyone above?"
4. **Book the next session** before leaving the room.
