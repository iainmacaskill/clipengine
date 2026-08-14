# Discovery interview — problem analysis (pass 1)

**Department:** Customer Success (Lead Forensics)
**Interviewees:** Nadean and Richard, Customer Success
**Interviewer:** Iain (AI Solutions Lead)
**Source:** Call transcript, single session (timestamped 00:00:39–01:27:01)
**Pass:** 1 of the discovery month — problems only. No evaluation of fixes, no solutions.

**Speaker attribution — INFERENCE.** The transcript labels voices only as Speakers 1–5. Reading: Speaker 2 asks the questions throughout → Iain. Speaker 1 refers to "as Nadine said" and speaks for department strategy → Richard. Speaker 3 owns the call-QA project and says "the most important opinion when it comes to call quality is mine" → Nadean. Speakers 4 and 5 make brief interjections and are unidentified. All attributions below carry this caveat. The transcript itself is imperfect (auto-transcription garbles); quotes are verbatim including errors.

---

## 1. Problem register

### P1. Call quality is checked on a tiny fraction of calls
- **Problem** — One person manually QAs calls; he covers 120 calls a month against roughly 400–500 customer meetings a week across ~40 CSMs, and the calls he reviews are chosen by monthly nomination. *(EVIDENCE)*
- **Their words** — Nadean: "we've got one QA person who can do 120 calls per month, versus this system that can do every single call per day." Richard: "we've got somewhere in the region of forty CSMs globally split across UK and US. They're doing around 500 meetings per week... we have one guy who currently sits at a desk and literally listens to a whole call recording, and then rates it on these 10 areas." Richard: "he can only do 120 calls a month. We're doing 400 meetings a week... The most he will be able to get through is like three or four for a CSM." Nadean on selection: "We just come up with the list at the end of each month for the following month, based on their tenure or risk."
- **Who feels it** — The QA person (Jack), team leaders coaching from the output, all ~40 CSMs being appraised. *(EVIDENCE for roles; the QA person's name "Jack" appears at 00:16:52 — "comparing it against Jack's QA")*
- **How often / how big** — 120 QA'd calls/month vs 400 or 500 meetings/week (both figures stated — see Tensions T1); 3–4 QA'd calls per CSM at most. *(EVIDENCE)*
- **Impact** — Coverage so thin that feedback is contestable (see P2); QA capacity is a hard ceiling. *(EVIDENCE for the numbers; the "ceiling" framing is INFERENCE)*
- **Where it lives** — Call QA step of the coaching process; Jiminny recordings, manual spreadsheet scoring ("he's putting that in the spreadsheet"). *(EVIDENCE)*
- **How much they care** — Richard calls the project addressing it "probably our most highest impact project." *(EVIDENCE)*

### P2. Feedback from a handful of calls gets dismissed as a one-off
- **Problem** — Because each CSM is judged on three or four calls, team leaders can and do wave the findings away, so coaching doesn't land. *(EVIDENCE)*
- **Their words** — Richard: "often what happens is you then give the feedback to the team leader, and you say, 'They were really rubbish on this call. They didn't set the agenda, or talk about goals.' And they'll say, 'Oh, yeah, I think that was a one-off.'"
- **Who feels it** — Team leaders and whoever delivers QA findings (Nadean/QA); ultimately the CSM whose behaviour doesn't change. *(EVIDENCE for the exchange; the downstream effect on CSMs is INFERENCE)*
- **How often / how big** — "often" (Richard's word); not quantified. *(GAP — see §5)*
- **Impact** — Coaching conversations stall on disputed evidence. *(EVIDENCE, per the quoted exchange)*
- **Where it lives** — Weekly team-leader coaching sessions. *(EVIDENCE: "Team Lead will have a coaching session with their team member every single week")*
- **How much they care** — Presented as the core rationale for the whole QA effort: "the whole point of doing it through AI is we can go, 'No, it's ten, twenty, thirty, forty calls, all been analysed.'" *(EVIDENCE)*

### P3. Human QA judgments differ from listener to listener
- **Problem** — Different reviewers score the same call differently, so QA outcomes depend on who listened. *(EVIDENCE)*
- **Their words** — Richard: "When you QA a call, I might listen to the call. They did do this very well, and then Nadine might listen to it and say, 'Well, I think they did okay...' and then you might listen to it and go, 'I can't see what you're both saying.'... It's how different people interpret the call."
- **Who feels it** — Anyone QAing (Jack, Nadean, team leaders) and CSMs being scored. *(INFERENCE from the quote's cast)*
- **How often / how big** — Not quantified. *(GAP)*
- **Impact** — Perceived fairness of appraisal; Iain reflected and Nadean confirmed that wider coverage "will appear more fair to the individual who's being appraised." *(EVIDENCE)*
- **Where it lives** — Manual QA scoring. *(EVIDENCE)*
- **How much they care** — Framed as "the whole thing with QA" (Richard). *(EVIDENCE)*

### P4. No view of a CSM's performance across their recent calls
> Note: this pain sits inside an in-flight fix (the AI call-QA workflow, §3.1). Recorded here because the speakers named it as their current top sticking point; the fix itself is not assessed in this pass.
- **Problem** — Individual calls get scored, but producing an average per CSM across their last 50 calls is not possible today; attempts top out around eight calls at a time, and average calculations have come out wrong. *(EVIDENCE)*
- **Their words** — Nadean: "The area we're having a challenge with at the moment is taking that information and working out, for the last 50 calls on average, what scores everyone achieved and what overall feedback their team leader needs to focus on with them... To work out an average of 50 calls at the moment, I've got up to eight calls that it's able to read and generate average feedback for." "We're at a real sticking point with it that it simply cannot process more than eight calls at a time, and we've tried Gemini, like GPT." "But again, you can only use it for eight calls max. At the moment, it's not particularly valuable." "We were just trying to get it to work out averages for all the scores, and it was completely inaccurate."
- **Who feels it** — Nadean directly; team leaders who need "what overall feedback their team leader needs to focus on with them"; department heads wanting cross-CSM comparison ("who is performing best when it comes to goals"). *(EVIDENCE)*
- **How often / how big** — Want: last 50 calls per CSM. Get: ~8. *(EVIDENCE)*
- **Impact** — Strength/improvement views "not particularly valuable"; cross-department gap analysis and best-performer identification blocked, in their telling. *(EVIDENCE)*
- **Where it lives** — PlanHat AI workflows over Jiminny transcripts. *(EVIDENCE)*
- **How much they care** — "a real sticking point." *(EVIDENCE)*

### P5. AI-generated call scores and feedback vary and are sometimes off
> Note: also lives inside the in-flight fix (§3.1); recorded because the speakers stated it as current pain, not as my assessment of the fix.
- **Problem** — Written feedback comes out differently on identical inputs, risk sentiment doesn't score as intended, and some scored calls have been flagged as wrong; a broader accuracy check is still outstanding. *(EVIDENCE)*
- **Their words** — Nadean: "the written feedback populates slightly differently every time because, of course, you could put the same prompt in multiple times, and it's always going to spit out something slightly different." "the risk sentiment at the moment isn't scoring the way that I wanted to." "Kayla flagged some calls to me yesterday that she thought were completely off." "I need to now do a bigger sense check and make sure that it's not hallucinating or anything like that. We literally just launched it on Monday afternoon."
- **Who feels it** — Nadean (owns validation), team leaders reading the scores, Kayla (flagged calls). *(EVIDENCE)*
- **How often / how big** — Not quantified; launched to team leaders "Monday afternoon" of interview week. *(GAP)*
- **Impact** — Trust in the scores; validation load on Nadean ("I'm going to give those a listen today"). *(EVIDENCE)*
- **Where it lives** — PlanHat QA workflow output fields. *(EVIDENCE)*
- **How much they care** — "There's been some really tricky areas"; "the goal is for it to become really reliable." *(EVIDENCE)*

### P6. Customer records in the CRM stay unfilled
- **Problem** — CSMs have the conversations but don't record basic customer facts in PlanHat; a field as simple as which CRM each customer uses has gone unfilled for two years. *(EVIDENCE)*
- **Their words** — Richard: "You got 100 customers, we need to know which CRM, every single customer use. And they don't fill it out. Just continually. In two years. Come on. Just ask in a call. What CRM do they use? It's not that difficult. They just don't. They do have that conversation." Speaker 5: "They don't update Planhat."
- **Who feels it** — Department leadership needing the data; the new CS data analyst's retention/ICP work depends on it ("we then want to link that information to our retention data"). *(EVIDENCE)*
- **How often / how big** — "Just continually. In two years." Otherwise unquantified (how many fields, what completeness rate). *(GAP)*
- **Impact** — Blocks linking customer attributes to retention to "help identify our sales and marketing missing people" — described as "a huge project." *(EVIDENCE)*
- **Where it lives** — PlanHat data entry after customer calls. *(EVIDENCE)*
- **How much they care** — Audible exasperation: "Come on... It's not that difficult." *(EVIDENCE)*

### P7. What sales learns about a customer doesn't survive the handover to CS
- **Problem** — CS has no access to sales call recordings, and human handovers omit or mis-state information, so customers repeat themselves, onboarding takes longer, and CSMs prep from incomplete or wrong facts. *(EVIDENCE)*
- **Their words** — Nadean: "our salespeople have all of these conversations with our customers throughout the sales process... We had zero visibility of what those calls looked like or what conversations took place, and the impact of that is that customers are needing to repeat themselves. The onboarding process can take a little bit longer." "the sales option [sic — likely 'salesperson'] leaves out a lot of the information, or they might pass over information that's incorrect. So the CRM [sic — likely 'CSM'] then says, 'Great.' So your CRM is Salesforce, and the customer might be like, 'No, it's not. where did you get that from?'" On Salesloft transcripts: "Yes, but we have no access to them. Salesloft isn't linked to anything else in the business I'm aware of." Richard on incentives: "generally once sales have made the sale they don't care anymore. THe irony being they get paid on renewals, so they should." *(Attribution of the "they don't care" line between Nadean and Richard is uncertain in the transcript.)*
- **Who feels it** — CSMs (prep time, credibility in front of the customer), customers (repetition), onboarding outcomes. *(EVIDENCE)*
- **How often / how big** — Not quantified. *(GAP)*
- **Impact** — "That's something we need to solve and save time. It'll save the CSM a lot of time with prepping, and it will just create a much more cohesive customer experience." *(EVIDENCE)*
- **Where it lives** — Sales→CS handover; Salesloft (sales-owned, unintegrated) vs PlanHat. *(EVIDENCE)*
- **How much they care** — Raised unprompted as "one more thing I want to put on your radar"; tied to a GRR project. *(EVIDENCE)*

### P8. Blind spots: nobody reliably knows which customers need attention
- **Problem** — With 80–220 customers per CSM, the business relies on each CSM's own account of their book; customers in a bad state have gone unspoken-to for months without anyone noticing. *(EVIDENCE)*
- **Their words** — Richard: "CSMs will have somewhere between eighty and two hundred and twenty customers, and you're relying on them to be on top of it." "what we find is, customer CSM, eighty customers, they're pretending everything's great." "You've got twenty customers. You haven't spoken to me for six months. I've seen some of their emails. They're in an absolute, really bad place. Why have you not spoken to these customers?" "There's a blind spot. There's blind spots everywhere."
- **Who feels it** — Department leadership (Richard speaking); disengaged customers; CSMs carrying 80–220 accounts. *(EVIDENCE)*
- **How often / how big** — Book sizes stated (80–220); the example cites 20 customers untouched for six months; overall frequency not quantified. *(PARTIAL — see §5)*
- **Impact** — Retention risk going unseen until late. *(EVIDENCE by context; the "until late" phrasing is INFERENCE)*
- **Where it lives** — CSM account prioritisation / book management. *(EVIDENCE)*
- **How much they care** — "an absolute, really bad place"; "blind spots everywhere." *(EVIDENCE)*

### P9. Hitting every activity metric doesn't predict retention — and they can't see why
- **Problem** — Some CSMs meet all activity metrics yet have poor retention; the department has no way to work out what actually separates good outcomes from bad. *(EVIDENCE)*
- **Their words** — Richard: "we have CSMs who hit all our metrics exactly. They're making the right number of calls, they're making the right number of meetings. They seem to have all the data about their customers." Nadean: "But their retention is poor... We think these are all the right things to be doing, but it may not be. But there's no way for us to figure that out."
- **Who feels it** — Department leadership; team leaders coaching to the metrics. *(EVIDENCE / INFERENCE respectively)*
- **How often / how big** — Not quantified. *(GAP)*
- **Impact** — Retention is repeatedly named the business's number one (and number two) priority: "What is number one priority in this business? Retention... 'What's the number two priority in the business? It's still retention.'" "Everything is retention." Retention described as "completely flat" over the last three years (no figure given). *(EVIDENCE)*
- **Where it lives** — Performance management and metric design across CS. *(EVIDENCE)*
- **How much they care** — "There's no way for us to figure that out" delivered as the punchline of the section; "leaky bucket" used for the consequence: "otherwise, you've got a leaky bucket and you're pouring all of this in at the front end." *(EVIDENCE)*

### P10. CSMs spend their time cleansing customer data and building setups by hand
- **Problem** — Customers hand over messy CRM exports; CSMs (often new starters) clean the data, dedupe domains, and build large filter/portal configurations manually, which is time-consuming and repetitive. *(EVIDENCE)*
- **Their words** — Richard, voicing the customer: "Oh yeah, well I've got the data out of my CRM system, but it's in a mess. Can you clean it for me?" and "I need you to set up fifty filters in Lead Forensics, all the different criteria, one filter per salesperson. Can you go and set these all up for me?" Nadean: "It can be very time consuming. Generally, we then get new starters to do it." "Once you've done it once, you don't really need to do it again. It's quite repetitive." "They use Copilot to help them cleanse the data, but Copilot can only cleanse so much at once." Richard on the Teams channel: "'Anyone that can help me with data mapping as I've got a new custome?.'" [sic]
- **Who feels it** — CSMs and new starters; the customer waiting on setup. *(EVIDENCE)*
- **How often / how big** — Not quantified per customer or per week. *(GAP — Richard suggests Vicky may dispute how big this is; see Tensions T6 and §5)*
- **Impact** — Nadean ties it to the commercial role: "we could have CSMs who are able to spend more time having really commercial conversations with their customers rather than having to do all of that data piece." Also links initial setup quality to product stickiness: "if we don't help them with that really strong initial setup, then it's just going to be used [sic — sense appears to be 'unused']." *(EVIDENCE)*
- **Where it lives** — Onboarding and ongoing account service; Excel/CSV work outside any system of record. *(EVIDENCE)*
- **How much they care** — "very time consuming"; "quite repetitive"; delegating to new starters signals low-value status. *(EVIDENCE; the last clause is INFERENCE)*

### P11. Call prep takes about five hours a week per CSM — and often doesn't happen
- **Problem** — Preparing for each customer call (surfacing portal data, checking the customer's website/LinkedIn, building a deck) takes ~20 minutes per call, ~5 hours per CSM per week; CSMs frequently go in unprepped and the call goes badly. *(EVIDENCE)*
- **Their words** — Nadean: "Or five or more hours per CSM per week... one of the problems we have is that they often will go into a call unprepped, which means that it's then a crap call and so on. It takes about five hours per week of CSM time." "So I would say every call I'm going to go into should take me about twenty minutes to prepare." "It's not about the deck. It's about going in and surfacing info, looking at their portal and website." "you need to look at multiple different places to find the info to be able to prep up for that call."
- **Who feels it** — All CSMs; customers on the receiving end of unprepped calls. *(EVIDENCE)*
- **How often / how big** — ~20 min/call; ~5 hrs/CSM/week; the department runs 400–500 meetings/week. (Note the same answer also contains "A little bit more than a couple of hours" — see Tensions T7.) *(EVIDENCE, with stated inconsistency)*
- **Impact** — "a crap call and so on"; unprepped calls feed the no-show cycle (see P12): "your last call wasn't any good, therefore it's not a good use of their time to join the next one." *(EVIDENCE)*
- **Where it lives** — Pre-call routine: Lead Forensics portal, customer website/LinkedIn, PlanHat history, deck building (PowerPoint). *(EVIDENCE)*
- **How much they care** — Nadean volunteered it as "a big one" ("The prepare decks for reviews is like a big one"). *(EVIDENCE)*

### P12. Around a third of booked customer meetings don't show
- **Problem** — Roughly one in three booked meetings isn't attended, against a target of 80% attendance; the prep is wasted, the hour is lost, and the meeting has to be rearranged. *(EVIDENCE)*
- **Their words** — Richard: "we've heard that about a third of meetings don't show. So there's also a lot of prep going into meetings... don't turn up." Nadean: "we should aim for an 80% attendance rate. Four out of every five calls should be joined." On causes: "One is that your last call wasn't any good, therefore it's not a good use of their time to join the next one. Or the second one is that... you haven't made the value obvious to them why they should jump on this call." On cost: "you're then taking up an hour of your time that you could have been on with a customer." Richard: "The point is, you're wasting time prepping the deck." Iain: "This has been a historic issue." Nadean: "Yeah, yeah."
- **Who feels it** — CSMs (lost hours, wasted prep); ultimately customer relationships. *(EVIDENCE)*
- **How often / how big** — "about a third" — flagged by Richard as second-hand ("we've heard"); target is 80%. *(EVIDENCE, but unverified — see §5)*
- **Impact** — Wasted prep and lost customer-facing time. *(EVIDENCE)*
- **Where it lives** — Meeting booking and pre-call engagement (the 48-hour touchpoint that should make value obvious). *(EVIDENCE)*
- **How much they care** — "It's not the end of the world, but again, it's obviously not ideal" (Nadean); confirmed as historic. *(EVIDENCE)*

### P13. Customers don't act on the data, don't see ROI, and cancel
- **Problem** — The customers' number-one challenge is commercialising the lead data (actually calling the businesses surfaced); where the buyer is marketing and sales doesn't adopt, or nobody's role includes calling the data, customers see no ROI and cancel. A sizeable segment is disengaged. *(EVIDENCE)*
- **Their words** — Nadean: "the number one challenge that we have with our customers is then commercialising that data and doing everything with it... if you're not picking up the phone and cold calling those businesses, getting them through your sales process, then you won't generate any ROI, any revenue. And if you don't generate revenue, you won't renew with Lead Forensics." On the buyer/user split: "sales don't listen to anything that marketing tells them to do." From the cancellation-call analysis: "the last 100 cancellation calls in Jiminny lack of internal adoption and resource" [sic]; "Perceived lack of ROI and value. Again, no evidence of ROI from the leads generated. Data quality and technical limitations." On the segment: "we've also got this big part of disengaged customers that we're really trying to get fresh off." [sic] On the standing objection: "Our number one objection that we get from our customers is, 'You can't show me the individual who's been on the website.'"
- **Who feels it** — Customers first; CS carries the retention consequence; save desk / annulment work exists because of it. *(EVIDENCE)*
- **How often / how big** — Cancellation-reason list drawn from "the last 100 cancellation calls"; size of the disengaged segment not stated. *(PARTIAL)*
- **Impact** — Cancellations; flat retention in a business where "Everything is retention" (5,000 customers, £40M/year stated). *(EVIDENCE)*
- **Where it lives** — Customer adoption after onboarding; the marketing-buys/sales-uses gap in the customer's own organisation. *(EVIDENCE)*
- **How much they care** — "leaky bucket"; retention named priority one and two. *(EVIDENCE)*

### P14. Analysing conversations in bulk is capped and manual
> Note: partially lives inside existing tooling (Jiminny) and the cancellation-analysis initiative (§3.12).
- **Problem** — Bulk analysis of calls tops out at 100 calls and one week of data, and can't be automated; the cancellation-call analysis hit the same many-calls-at-once wall. *(EVIDENCE)*
- **Their words** — Nadean: "We can also do bulk analysis in Jiminny. It can do up to 100 calls at a time." Richard: "But it only does 100. and only for one week." Nadean: "And it's all done manually. There's no way to automate this." Richard on cancellation analysis: "We have done a bit of work again using AI to try and analyse a whole load of cancellation calls... that's been reasonably successful. But, we've had problems with it, can't you do so many calls at once?"
- **Who feels it** — Whoever runs cross-call analysis (Nadean; Vicky's cancellation work). *(EVIDENCE)*
- **How often / how big** — Caps stated (100 calls / one week); frequency of need not stated. *(PARTIAL)*
- **Impact** — Limits pattern extraction (cancellation reasons, product feedback themes). *(EVIDENCE by context)*
- **Where it lives** — Jiminny bulk analysis; ad-hoc AI analysis of cancellation calls. *(EVIDENCE)*
- **How much they care** — Stated matter-of-factly; no severity words. *(EVIDENCE of tone)*

### P15. The transcript pipeline itself wobbles: delays and wrong-account matches
- **Problem** — Transcript processing is usually minutes but degrades to hours or days when Jiminny has server glitches, and transcripts link to the correct customer account only in the mid-to-high-ninety percent range. *(EVIDENCE)*
- **Their words** — Nadean: "sometimes they have glitches with their servers and it can take longer... When it's not working effectively, it can take hours or days." "it also links to the correct account. In theory, although we have also had some issues with that, where we're in the mid to high nineties of accuracy with connecting to the correct customer."
- **Who feels it** — Everything downstream of transcripts (QA scoring, CRM population, risk scoring). *(INFERENCE)*
- **How often / how big** — "sometimes"; failure rate implied at roughly the low single-digit percent of calls (from "mid to high nineties"); neither pinned down. *(PARTIAL)*
- **Impact** — Not stated explicitly. *(GAP)*
- **Where it lives** — Jiminny recording/transcription and the hourly Jiminny→PlanHat integration ("fires a quarter past the hour"). *(EVIDENCE)*
- **How much they care** — "it's not perfect, but it's really decent" — mild. *(EVIDENCE)*

### P16. Customers can't keep their uploaded data current; the automated route is down
- **Problem** — Customers must manually re-upload lists whenever their pipeline changes; the product's automated data upload function was recently changed and isn't working. *(EVIDENCE)*
- **Their words** — Nadean: "First way is manual. So every time my sales pipeline changes or my list of customers changes, I then have to re-update it. However, we do have an automated data upload function within the product. But where we recently changed it, that function isn't quite working yet. But it's due to be up and running in the next couple of months."
- **Who feels it** — Customers; CSMs who do it for them ("initially we configure everything for them"). *(EVIDENCE)*
- **How often / how big** — "every time my sales pipeline changes"; not quantified. *(GAP)*
- **Impact** — Stale customer data in the product; feeds the P10 service burden. *(INFERENCE)*
- **Where it lives** — Lead Forensics product (business lists / data upload). *(EVIDENCE)*
- **How much they care** — Stated flatly, with a fix expected "in the next couple of months." *(EVIDENCE)*

### P17. The call-QA process exists only as product workflows — nothing written down
- **Problem** — The AI QA process, unlike CSM induction and call training, has no documentation; it lives solely as configured workflows in PlanHat that one person can walk through. *(EVIDENCE)*
- **Their words** — Nadean: "We don't have that documented... I guess technically it's because it's all workflows." Richard: "It's a workflow, in the products. But it's not documented." Nadean: "I could easily just like walk you through it."
- **Who feels it** — Not stated. *(GAP; single-person dependency is INFERENCE)*
- **How often / how big / Impact** — Not stated. *(GAP)*
- **Where it lives** — PlanHat workflow configuration. *(EVIDENCE)*
- **How much they care** — Treated lightly in the room ("That's good." / laughter implied). *(EVIDENCE of tone)*

### P18. Nobody in the room could state the AI cost basis with confidence
- **Problem** — The PlanHat credit allowance, its price, and its unit of time were all uncertain in the conversation (one vs two million credits; per month vs per year; £20k vs £25k), and capacity planning has been "back of a post-it." *(EVIDENCE)*
- **Their words** — Nadean: "How much was that? Was it 20 grand a year? 20, 25 grand." Richard: "Now I think we're getting two million credits... is it two million or one million? We got one million. Was it two?... I think it was one million... that's a million a month. Isn't it?" Later: "It's not two million. It's a million a month." On forecasting: "we kept saying, 'Well, how many will this take?' And they said, 'Well, depends what model we use.'" Iain: "Back of a post-it calculation." Richard: "Just very much that." Observed consumption: "This is run. It does a thousand times, and it's used forty, nearly forty-four thousand credit" (Nadean).
- **Who feels it** — Whoever must scale QA "to everybody all the time for everything" within the credit budget. *(INFERENCE)*
- **How often / how big** — ~44,000 credits per 1,000 runs stated; allowance stated (uncertainly) as 1M/month for ~£20k/year. *(EVIDENCE, contested — see Tensions T2)*
- **Impact** — Not stated by the interviewees. *(GAP)*
- **Where it lives** — PlanHat contract and credit metering. *(EVIDENCE)*
- **How much they care** — Low urgency in the room; uncertainty itself is the observation. *(EVIDENCE of tone)*

---

## 2. Solution-talk, translated back

All items below are **DERIVED**: the interviewee named a remedy; the underlying problem is my reading and must be confirmed with the speaker before entering the register.

1. **Remedy named** — "what we also want is an overall dashboard that allows me to see, for Rich, for this month on average, what did Rich score for every call area?" (Nadean). **Implied problem** — there is no per-CSM, per-area performance view over time. *(Overlaps P4, which is independently evidenced.)*
2. **Remedy named** — "What we would love is a system that just said, this week, this CSM needs to speak to these ten customers" and "the AI says this week these are the hundred customers you need to focus on" (Richard). **Implied problem** — no trustworthy, proactive prioritisation of accounts; reliance on CSM self-management. *(Overlaps P8.)*
3. **Remedy named** — "Something AI could do is automate that email 48 hours beforehand... that gives the customer a compelling reason to jump on that call" (Nadean). **Implied problem** — pre-call value-add emails are not being sent consistently, and no-shows follow. *(Overlaps P12.)*
4. **Remedy named** — "take all of those call recordings and create a handover document that gives the CSM everything they need to know about that customer" (Nadean, re Salesloft). **Implied problem** — handover information is incomplete/incorrect and sales-call knowledge is inaccessible. *(Overlaps P7.)*
5. **Remedy named** — "what we want to get to is the ability to do that within PlanHat within our CRM. So that we're using one system for everything, we're not having to say to people, 'We'll go here and do this, and go here and do this'" (Nadean). **Implied problem** — staff juggle multiple systems to do one job.
6. **Remedy named** — "we're considering bringing all transcripts from Jiminny and all transcripts from SalesLoft into an area that Cyclone manages, and sort of having one central repository of every single transcript" (Richard). **Implied problem** — conversation records are fragmented across sales- and CS-owned systems.
7. **Remedy named** — "We also need to roll out a QA for our team leaders... We now need to QA those PTB meetings" (Nadean; PTB = "Protect the Book", three per CSM per week). **Implied problem** — no visibility of the quality of team-leader PTB meetings. *(Timescale stated: "going to be happening in the next six months.")*
8. **Remedy named** — "Planhat does have the ability to automatically create presentations. We haven't really done that... Most of that data is in Planhat, so you should just be able to push it up as you go. Creat deck" (Richard). **Implied problem** — deck assembly is manual even where the data already sits in the CRM. *(Overlaps P11.)*
9. **Remedy named** — "If we could put in somewhere, for example. Bob is a sales director... Based on that information, go into the Lead Forensics portal, pull out the interesting stuff that pertains to what Bob really cares about, put that into a deck for me... That would be amazing" and "If we could have AI surfacing that... that would just be game changer" (Nadean). **Implied problem** — customer-specific signals (new hires, portal activity) are not surfaced to CSMs; each CSM assembles context manually. *(Overlaps P11.)*
10. **Remedy named** — "We want AI to be able to identify either additional websites that the company has, or if they're part of a group of companies, who are the group companies... At the moment we ask our CSMs to identify leads. What we're moving to is have AI identify the leads" (Richard, NRR/expansion — currently sales-owned). **Implied problem** — expansion opportunities depend on CSMs spotting them manually, and the company's corporate-structure knowledge of its customers is incomplete ("we might not know").
11. **Remedy named** — "We need the AI to be able to know who the CSM is" (Richard, quoting Paul the CEO, re the Zendesk chat agent). **Implied problem** — the support channel can't answer account-specific questions a human agent could look up. *(Lives inside an existing fix, §3.6.)*

---

## 3. Existing fixes — parked, not analysed

Named owner as stated in the transcript; "—" where none was named.

1. **AI call QA scorecard** — Jiminny transcripts pulled into PlanHat hourly; workflow scores each success-review call on ~10 areas with written feedback (Gemini 2.5 Pro; prompt document defines "what good looks like"). Launched to team leaders the Monday before the interview. Owner: Nadean.
2. **Manual call QA** — one person listening to nominated calls, scoring 10 areas out of five into a spreadsheet, 120 calls/month. Owner: Jack (QA person).
3. **Weekly coaching cadence** — TL + CSM session every week; CSM self-reviews own call, TL brings QA feedback, goals set. Owner: team leaders (process).
4. **CRM auto-population from transcripts** — using call transcripts to fill customer fields (CRM used, team size, use cases) in PlanHat. Owner: — (CS initiative, described by Nadean/Richard).
5. **PlanHat native risk scoring** — AI rates every synced conversation/email/ticket, rolls up a −100…+100 score per customer over 90 days; CS categorises into good place / monitor / call. Owner: — (native PlanHat feature; CS applies the bands).
6. **Zendesk AI chat agent** — live in product about a month; handles ~100–150 of ~600–700 monthly tickets; does real-time translation. Owner: Brent (support manager) named in context; quality bar set by Paul (CEO).
7. **Ad-hoc Salesloft→handover document via Claude** — a US colleague converting sales transcripts into handover docs ("a bit too long, but really good"). Owner: unnamed US team member.
8. **Cyclone central transcript repository (under consideration)** — pulling Jiminny + Salesloft transcripts into an area Cyclone manages. Owner: Ed (Cyclone); Michael (sales operations) also named.
9. **Customer/group analysis engine and SDR-agent exploration** — "Mateo has built an AI engine that's doing this" (group companies / additional domains); also "started looking at SBR [sic] AI agents." Owner: Mateo (Chief Revenue Officer).
10. **UserGems** — stakeholder-change tracking (alerts when customer contacts change roles). Owner: — (in use).
11. **Copilot pre-call research prompt** — standard prompt Nadean issues to CSMs to research website/LinkedIn before onboarding calls. Owner: Nadean.
12. **Cancellation-reason analysis** — list built from "the last 100 cancellation calls in Jiminny" ("Vicky's cancellation" work). Owner: Vicky named in connection with it.
13. **New CS data analyst** — hired to link customer attributes to retention data (ICP identification). Owner: — (reports within CS; Richard described the hire).
14. **Save desk and annulment projects** — pre-cancellation prevention and post-cancellation recovery workstreams. Owner: Nadean ("I've got two main pots that I'm working on").
15. **Automated data upload function** — in-product customer data upload; recently changed, due "up and running in the next couple of months." Owner: — (product).
16. **Supporting stack (for reference, as recited for the recording)** — Jiminny (call recording), PlanHat (CS CRM), Cyclone (internal CRM/revenue engine), Teams, Outlook, UserGems, Zendesk, Skilljar (customer academy), Calendly, PandaDoc; CRM integrations (Salesforce, HubSpot, Dynamics, others via Zapier); business lists feature; partner prospecting agencies.

---

## 4. Tensions

- **T1. Weekly meeting volume.** Richard: "They're doing around 500 meetings per week" (00:04:01) vs "We're doing 400 meetings a week" (00:05:03) and "The CSMs are having Four hundred meetings a week" (01:08:06). Same speaker, both unreconciled.
- **T2. The PlanHat credit contract.** "Now I think we're getting two million credits" and "this is all Plan Hat and two million credits for twenty thousands" vs "It's not two million. It's a million a month"; "Was it 20 grand a year? 20, 25 grand"; "Twenty thousand pounds. I think it was one million." Amount, unit and price all moved during the conversation.
- **T3. Is the AI QA consistent?** Richard: "getting everyone to agree the AI is consistently doing it fair. If that's part of your challenges, I think we pretty much got it nailed" vs Nadean, in the same minutes: "Kayla flagged some calls to me yesterday that she thought were completely off"; "the risk sentiment at the moment isn't scoring the way that I wanted to"; "the written feedback populates slightly differently every time."
- **T4. The handover process on paper vs in practice.** Official process (Richard): "They sit with the CSM and go over their customer knowledge from their sale... when the CSM does the first boarding call with the customer, the salesperson joins and reconfirms... it's a nice handover. Good customer experience." Practice (Nadean): "the sales option leaves out a lot of the information, or they might pass over information that's incorrect"; and "once sales have made the sale they don't care anymore" — despite "they get paid on renewals, so they should."
- **T5. Attendance target vs reality.** Target (Nadean): "we should aim for an 80% attendance rate." Reported reality (Richard, second-hand): "we've heard that about a third of meetings don't show."
- **T6. Hands-on data service: burden or advantage?** Nadean: it prevents CSMs "having really commercial conversations", yet "if we don't help them with that really strong initial setup, then it's just going to be used [sic]" — the same service is both the problem and the safeguard. Richard separately hedges scale: Vicky "might say, 'Do you know what? We've got it pretty well covered'" while he sees "lots of conversations about people spending lots of time crunching data in Excel spreadsheets."
- **T7. Prep-time figure.** Within one answer (Nadean): "five or more hours per CSM per week. A little bit more than a couple of hours. if they're prepping properly... It takes about five hours per week of CSM time." The five-hour figure recurs and is consistent with "about twenty minutes" per call at three meetings/day, but "a couple of hours" sits unresolved beside it.
- **T8. Transcript turnaround.** "Generally, it's quite quick... Oh no, minutes still" vs, moments later, "When it's not working effectively, it can take hours or days."
- **T9. Team count.** Richard: "Seven, eight. Eight." Nadean, counting: "Enterprise R three, three in the U.S., three in the UK, R one and two. Seven." (Transcription garbled; count unresolved.)

---

## 5. Still to learn

### Quantification gaps — question to ask, and who
| Gap | Follow-up question | Ask |
|---|---|---|
| Meetings per week (400 vs 500) | "From the calendar/Jiminny data, how many customer meetings did CS actually hold per week over the last quarter?" | Richard, or the new CS data analyst |
| No-show rate ("we've heard about a third") | "What was the actual attended-vs-booked rate last quarter, by team?" | Team leaders / data analyst (Richard flagged the figure as hearsay) |
| How often QA feedback is disputed as a "one-off" | "In the last month of coaching sessions, how many QA findings were challenged or discounted?" | Team leaders; Nadean |
| Prep time ("a couple of hours" vs "five or more") | "Can we time-sample a week of prep across a few CSMs?" | Nadean; team leaders |
| Data-cleansing burden per new customer | "How many hours does a typical onboarding data cleanse/filter build take, and how many happen per month?" | Vicky (heads the UK onboarding team — Richard explicitly routed this question to her) |
| Size of the disengaged-customer segment | "How many of the 5,000 customers sit in the 'disengaged' pot today?" | Nadean |
| Retention figure ("completely flat" — no number) | "What is the current GRR figure and its three-year trend?" | Richard / Tom James |
| PlanHat credit contract | "What exactly does the contract say — credits, period, price?" | Contract owner (unnamed in transcript) |
| Wrong-account transcript matches ("mid to high nineties") | "How many calls per month link to the wrong customer, and what happens to them?" | Nadean |
| Jiminny delay frequency ("sometimes... hours or days") | "How often in the last six months did transcripts arrive late, and what broke downstream?" | Nadean |
| Internal share of support tickets ("about half") | "Is the internal ticket load a problem worth solving, or working as intended?" | Brent (support manager) |
| Number of teams (seven vs eight) | "How many CS teams are there, exactly, and how are they split?" | Richard |

### People named but not yet interviewed
- **Ed** — owns Cyclone and the possible central transcript repository ("you could speak to Ed about where that project is").
- **Michael** — sales operations; named alongside Ed for Salesloft/Cyclone questions.
- **Mateo** — CRO; AI customer-analysis engine and SDR-agent exploration ("Can speak to them much" [sic]).
- **Vicky** — heads the UK onboarding team; owns the data-cleansing reality check and the cancellation-analysis list.
- **Jack** — the manual QA person; the day-to-day of the current QA process.
- **Kayla** — flagged AI-scored calls as "completely off"; first-hand view of score quality.
- **Tom James** — took over CS three years ago; the three-year "building period" and retention picture.
- **Brent** — support manager; Zendesk AI and ticket mix.
- **The unnamed US colleague** — built the Claude handover-document prototype.
- **Team leaders and CSMs** — the pain of P2, P8, P10, P11, P12 is attributed to them; none interviewed yet.
- **The new CS data analyst** — retention/ICP linkage work.
- **Paul (CEO)** — quoted as setting the quality bar for support AI; constraint-setter rather than problem-holder.

### Skirted or left hanging
- **The risk-detection "issues".** Iain referenced pre-interview notes: "The next one was one you said you had more issues with about AI risk detection." The issues themselves were never detailed — the conversation described how the feature works instead. Follow up with Richard/Nadean.
- **Unsanctioned tool use.** Richard, on the US colleague's Claude work: "We're not meant to use. We're not meant to be." — trailed off and not probed. Worth understanding what tooling is and isn't sanctioned, and why the workaround exists.
- **Salesloft↔Cyclone linkage.** Richard: "I'm not sure really what happens between Cyclone and Sales Loft if there's anything." Unknown even to the department lead; Ed/Michael question.
- **Retention numbers.** "Completely flat" over three years, £40M/year, 5,000 customers — but no retention percentage was given.
- **"Dean's last fifty calls" / "Dean said..."** — the transcript names Dean/Lottie/Angela/Natalie/Rod as apparent CSM examples, but "Dean" may be a mis-transcription of "Nadean" in places. Attribution of the tenure-based call-cadence rule needs confirming.

---

## 6. Draft problem statement for sign-off

For the department lead to confirm: *"yes, those are our problems."*

- We quality-check almost none of our customer calls. One person reviews 120 a month against roughly 400–500 meetings a week, so most CSMs are judged on three or four calls — and that feedback is easily dismissed as a one-off, and varies with who listened.
- We cannot see how any CSM performs across their recent calls as a whole, so team leaders coach without a fair, evidenced picture of strengths and weaknesses, and the department can't see its collective gaps.
- What the sales team learns about a customer largely fails to reach Customer Success. Handovers omit or mis-state information, sales call records are inaccessible to CS, customers repeat themselves, and onboarding takes longer than it should.
- CSM time is consumed by manual work around the calls themselves: about five hours a week each on call and deck prep, plus cleansing customer data and building portal setups — and around a third of booked meetings don't show, wasting that prep. Calls that aren't prepped go badly, which feeds the next no-show.
- We don't reliably know which customers need attention. With 80–220 accounts per CSM we depend on each CSM's own account of their book; customers in a bad place have gone unspoken-to for months, and CSMs who hit every activity metric can still have poor retention — with no way to see why. In a business whose first and second priority is retention, that is the blind spot that hurts most.
- Our customer records stay incomplete because the facts learned on calls don't get recorded — basic fields like which CRM a customer uses have sat empty for two years — so work that depends on knowing our customers (risk spotting, prioritisation, linking attributes to retention) is built on missing data.
