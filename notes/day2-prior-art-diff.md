# Day 2 addendum — our logic vs the two reference compliance checkers

*Written 2026-09-02, before labelling. Read this before you label: three of the
findings change what a correct label looks like.*

---

## What was compared

**Ours:** `src/aiact/obligations.py` and the tier ladder in `notes/project1-spec.md` §3.

**Theirs — two tools, and the second one matters more:**

1. **Future of Life Institute — EU AI Act Compliance Checker.** Unofficial,
   free, the long-standing reference tool; the site reports >150k users/month.
   Read via its published flowchart of the full form logic
   (`AI-Act-Compliance-Checker-Flowchart-v1.0_compressed.pdf`, v1.0, July 2025).
   https://artificialintelligenceact.eu/assessment/eu-ai-act-compliance-checker/
2. **European Commission / AI Office — the *official* AI Act Compliance
   Checker**, on the AI Act Service Desk. Currently **beta**. Every question
   carries its Article and Recital citations inline.
   https://ai-act-service-desk.ec.europa.eu/en/eu-ai-act-compliance-checker

**Evidence quality.** The FLI flowchart was read via an automated extraction, so
treat its article numbers as leads. The Commission tool was walked by hand,
question by question, so the citations recorded from it below are quoted from
the tool itself. Both are still secondary sources: verify against the text.

---

## 1. Prior art — and why Project 1 survives it

The Commission shipping its own checker is a bigger fact than FLI's. It means
"I built an EU AI Act classifier" is, on its own, a dead sentence in an
interview. Both the reference tool and the official tool already exist and are
free.

What neither of them does is **read a document**:

| | Both checkers | Project 1 |
|---|---|---|
| Input | A human answers a branching questionnaire | Unstructured text — a vendor page, a DDQ answer |
| Who judges | The human, before they start | The model, from the text |
| Output | One result, one system, one role at a time | A structured row; forty documents become forty rows |
| Under-specified input | Impossible — a form cannot be vague | `insufficient_information` + the gap questions for the vendor |
| Batch | No | The entire point |

They are decision trees for someone who already knows the answers. Ours reads
the answers out of the document. Someone holding forty vendor descriptions
cannot run either tool forty times — that is the inventory use case, and it is
what the ten-second test protects.

**Positioning consequence:** name both tools in the README and in the interview
answer, and say what ours does that they don't. Having surveyed the field reads
better than not having. There is also a legitimate framing available: Project 1
is a **triage front-end** that turns documents into rows, and the official
checker is where the ten interesting rows get confirmed by a human.

**One more thing to steal, not to fear:** the official tool cites Article and
Recital numbers on every single question. That is exactly the credibility move
`legal_basis` is for. Match it.

---

## 2. Findings — three gaps, all three now confirmed in the official tool

### 2.1 Article 6(3) derogation — missing from our ladder. Highest priority.

The official checker has a dedicated step, **"Derogations Annex III"**, cited to
**Article 6(3)**, asking whether the system is exempt from high-risk because it
does not pose a significant risk of harm. Its four limbs, as worded there:

- intended to perform a **narrow procedural task**;
- intended to **improve the result of a previously completed human activity**;
- intended to **detect decision-making patterns or deviations** from prior
  patterns, and not meant to replace or influence the previously completed human
  assessment without proper human review;
- intended to perform a **preparatory task** to an assessment relevant to an
  Annex III use case.

And the carve-out, in the tool's own words: an Annex III system **shall always
be considered high-risk where it performs profiling of natural persons**.

Our ladder goes Annex III → high risk, with no derogation step and no profiling
carve-out. This is the most important false-positive control in the Act, and
spec §3 already named the risk — *"the classifier must resist the pull toward
high-risk"* — then built a ladder that cannot express the remedy.

Still to verify in the text: that a provider claiming the derogation must
document the assessment and register the system anyway (Art. 6(4)).

**Why this must land before labelling.** A shortlist-anomaly tool that a human
reviews may well be derogated. Labelling 20 descriptions against a ladder with
no derogation step bakes the false-positive bias into the ground truth, and
Day 13 then measures the wrong thing with no way to see it.

### 2.2 Role escalation — and now we have the article number

FLI asks it first (`#E2`). The official tool has a step titled **"Responsibilities
along the AI value chain"**, cited to **Article 25** and Recitals 84, 87, 88 and
89: as a downstream distributor, importer, deployer or third party, have you

- put your **name or trademark** on the AI system,
- made a **substantial modification** to a system already placed on the market,
- **modified the intended purpose** such that it becomes high-risk?

Any of those and you become the provider — the Art. 16 obligation set, not
Art. 26.

> **Corrected 2026-09-02 against the Act itself — see `notes/day2-act-review.md` §C2.**
> Article 25(1) is bound to **high-risk** systems: (a) covers putting your name on a
> *high-risk* system, (b) a substantial modification of one that *remains* high-risk,
> (c) a purpose change that *makes* a system high-risk. White-labelling a minimal-risk
> tool does **not** escalate. The paragraph below overstated it.

We handle this only for GPAI fine-tuning, inside `_GPAI_NOTE`. A ManCo
white-labelling a vendor tool escalates too, with no model involved, and
`obligations_for(HIGH_RISK, DEPLOYER, ...)` then returns a complete-looking,
wrong list — the same class of error as the Art. 50 bug, one layer up.

**Design change:** `our_role` should stop being a raw input to the lookup. Asked
role + the Art. 25 modification question → *effective* role. Both belong in the
record; the delta between them is interesting on its own.

### 2.3 Article 2 scope — we have no "out of scope" outcome

The official tool spends **two** steps on this before it ever looks at risk:

- **"Are you within the scope of the AI Act?"** (Article 2, Recitals 21–22):
  placed or put into service in the EU · established or located in the EU ·
  output used in the EU · integrated into your product under your own name.
- **"Out of scope: excluded systems"** (Article 2, Recitals 22, 23, 25):
  military/defence/national security · third-country public authorities in law
  enforcement cooperation · **sole purpose of scientific research and
  development** · **research, testing or development activity not yet placed on
  the market or put into service**.

Our five tiers cannot express any of this. An excluded system comes back
`minimal_risk` — a weaker, different, and wrong claim than "the Act does not
apply".

The last two exclusions are the ones that bite a ManCo: an internal proof of
concept may be out of scope entirely. This is a legitimate scope choice either
way — add the outcome, or declare Art. 2 out of Project 1 in the README. But
decide it; don't leave it silent.

---

## 3. Two confirmations worth having

**Our Article 50 fix matches theirs.** FLI's transparency table keys on function
*and* entity — deepfakes → deployer, manipulated public-interest text →
deployer, emotion recognition and biometric categorisation → deployer, direct
interaction → provider, synthetic content → provider. Same per-paragraph model
`_ART50` was rebuilt around after the chatbot-deployer bug. Independent
confirmation that keying on `(tier, role)` alone was wrong.

Interview beat: found it in the first real run, traced it to hand-written Python
rather than the model, fixed it, and both reference implementations agree.

**`insufficient_information` is not a hack — the official tool does the same
thing.** Its questions offer **"Uncertain"** as a first-class answer alongside
Yes and No (on the AI-system definition and on high-risk classification). The
Commission's own tool treats "we cannot tell yet" as a real state rather than an
error. That is the design decision spec §2 makes, and it is now defensible by
reference rather than by argument.

---

## 4. Smaller cleanups

- **Split importer and distributor.** `_HIGH_RISK_DISTRIBUTION` cites
  "Art. 23/24" for both. FLI separates importer → **Art. 23**, distributor →
  **Art. 24**. A slash in a citation is careless on a regulator-facing tool.
- **GPAI: split Art. 53 from Art. 55.** FLI gates systemic risk on >10^25
  floating-point operations or a Commission determination; `_GPAI_NOTE` is one
  undifferentiated block. Cheap, and it reads as expertise.
- **Our Art. 27 line is better than FLI's — keep it.** Their summary names
  public bodies and private providers of public services; ours also names
  creditworthiness assessment and life/health insurance pricing, believed
  correct under Art. 27(1). Verify, then keep.
- **Annex I.** Both tools route Annex I products through a sector-specific /
  third-party-conformity question before Annex III. Spec §6 scopes Annex I out
  for a ManCo — now that the structure is known, write that down as a decision
  rather than leaving it as silence.
- **`product_manufacturer` and `authorised_representative`** appear in both
  tools' role lists and not in our `Role` enum. Almost certainly right to
  exclude for a ManCo; record it as a scope decision in the spec.
- **Multiple roles at once.** Both tools say the same thing: if you hold more
  than one role, run the assessment once per role. Our single `our_role` field
  cannot represent a ManCo that is both deployer and provider. Decide whether a
  record is per-(system, role) rather than per-system.

---

## 5. The §4 open item is CLOSED (resolved 2026-09-02)

Checked on EUR-Lex directly. **Regulation (EU) 2026/1744** of 8 July 2026
(Digital Omnibus on AI), OJ L series 24 July 2026, **in force 27 July 2026**.
It amends Regulation (EU) 2024/1689. Art. 113(3)(c) as amended: **2 December
2027** for Annex III high-risk, **2 August 2028** for Annex I embedded. Art. 50
is in Chapter IV and was not moved.

`https://eur-lex.europa.eu/eli/reg/2026/1744/oj`

The dates in `obligations.py` were already right. What was missing: the two new
Art. 5 prohibitions, applying 2 December 2026. See `notes/day2-act-review.md`.

## 6. What this changes, and in what order

1. **Art. 6(3) derogation** — schema field + prompt question + the profiling
   carve-out. **Before labelling.**
2. **Role escalation (Art. 25)** — asked role vs effective role, plus the
   modification question in the prompt. **Before labelling.**
3. **Art. 2 scope** — add an out-of-scope outcome, or declare it out in the
   README. **Decide before labelling**, even if the decision is "out of scope".
4. §4 cleanups — `obligations.py` only, no schema change, can follow.
5. §5 — EUR-Lex check, still owed, before Day 4.

Items 1–3 are roughly an hour or two. They must land before the 20 descriptions
are labelled; everything else can wait until after.
