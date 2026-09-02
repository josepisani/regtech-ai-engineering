# Day 2 review — our logic against the AI Act itself

*2026-09-02. Source: the **consolidated** text of Regulation (EU) 2024/1689 as
at **27 July 2026** — i.e. as amended by the Digital Omnibus on AI, Regulation
(EU) 2026/1744.*

`https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02024R1689-20260727`
(header reads `02024R1689 — EN — 27.07.2026 — 001.001`; passages marked `▼M1`
are Omnibus amendments)

Every article below was read in that text, not in a summary. Where our code and
a reference checker disagreed with the Act, the Act wins — that is the rule this
review was run under. Note EUR-Lex's own caveat: the consolidated text is a
documentation tool with no legal effect; the authentic versions are the OJ ones.

---

## A. Confirmed correct — do not touch

| Ours | Verified against |
|---|---|
| Annex III **4(a)** recruitment/selection — "place targeted job advertisements, analyse and filter job applications, evaluate candidates" | Annex III, point 4(a) |
| Annex III **4(b)** work-relationship decisions, promotion/termination, task allocation, monitoring | Annex III, point 4(b) |
| Annex III **5(b)** creditworthiness / credit score | Annex III, point 5(b) |
| Annex III **5(c)** risk assessment and pricing in life and health insurance | Annex III, point 5(c) |
| Spec's example citation **Art. 5(1)(f)** = inferring emotions in the workplace and education institutions | Article 5(1), point (f) |
| `_HIGH_RISK_DEPLOYER` Art. 26(1), (2), (4), (5), (7) | Article 26, those paragraphs |
| Art. **26(6)** logs kept "for a period appropriate to the intended purpose … of at least six months" | Article 26(6), verbatim |
| Art. **27** FRIA covering deployers of Annex III **5(b) and (c)** — more complete than FLI's summary | Article 27(1) |
| Art. **50(2)** grace period: providers of systems generating synthetic content placed on the market before 2 Aug 2026 comply by **2 Dec 2026** | Art. 113(4), inserted by 2026/1744 |
| Post-Omnibus application dates (2 Dec 2027 Annex III, 2 Aug 2028 Annex I) | Art. 113(3)(c)(i) and (ii) as amended |
| Art. 6(1) Annex I route requiring third-party conformity assessment (which the spec scopes out) | Article 6(1)(a) and (b) |

---

## B. The domain find — the financial-fraud carve-out

**Annex III point 5(b)** reads:

> AI systems intended to be used to evaluate the creditworthiness of natural
> persons or establish their credit score, **with the exception of AI systems
> used for the purpose of detecting financial fraud**.

Nothing in our spec or code carries that exception. For a ManCo it is the single
most useful sentence in Annex III: AML, transaction-monitoring and fraud-
detection tooling that scores natural persons is **not** high-risk on the 5(b)
limb. That is precisely the false positive spec §3 warns about — and a generic
classifier, having been told "credit scoring is high-risk", will get it wrong.

Put it in the prompt and in a few-shot example. It is also a strong interview
line: most people quoting Annex III 5(b) have never read to the end of it.

---

## C. Corrections — where we say more, or less, than the Act

### C1. `UNIVERSAL` over-applies Article 4, and overstates it

Article 4(1): "**Providers and deployers** of AI systems shall take measures to
support the development of AI literacy of their staff and other persons dealing
with the operation and use of AI systems on their behalf…" — and, added by the
Omnibus: "**This obligation does not require providers or deployers to guarantee
any specific level of AI literacy of any individual.**"

Two problems:

- Article 4 binds **providers and deployers only**. `UNIVERSAL` is added for
  every role, importers and distributors included. The comment above it — "the
  one obligation nobody escapes" — is not what the Act says.
- Our text says "**ensure** staff … have **sufficient** AI literacy". The Act
  says take measures to support development of it, and expressly disclaims any
  guaranteed level. Ours is stronger than the law.

**Fix:** reword to the statutory language, and gate `UNIVERSAL` on
`role in (PROVIDER, DEPLOYER)`.

### C2. Article 25 escalation is bound to high-risk — my earlier note overstated it

Article 25(1) makes a distributor, importer, deployer or other third party a
provider **"of a high-risk AI system"**, in three circumstances:

- (a) they put their name or trademark on a **high-risk** AI system already
  placed on the market or put into service, *without prejudice to contractual
  arrangements stipulating that the obligations are otherwise allocated*;
- (b) they make a **substantial modification** to a **high-risk** AI system
  already on the market, such that it **remains** high-risk under Article 6;
- (c) they modify the **intended purpose** of an AI system, including a
  general-purpose AI system, **not** classified as high-risk, such that it
  **becomes** high-risk under Article 6.

So white-labelling a *minimal-risk* vendor tool does **not** trigger Art. 25(1).
`notes/day2-prior-art-diff.md` §2.2 said it did; that was wrong and is corrected
here. The escalation question still belongs in the prompt — but it only changes
the obligation set on the high-risk path, or where the modification pushes a
system onto it.

Also worth encoding, from **Article 25(2)** (as amended): once escalation
occurs, "the provider that initially placed the AI system on the market … shall
no longer be considered to be a provider of that specific AI system", and must
cooperate and provide information and technical access to the new provider.
For a ManCo that is a contract point, and a good `gaps` question.

### C3. `_ART50` assigns duties to roles the Act does not bind

Read in Article 50:

| Paragraph | Whom it binds | What |
|---|---|---|
| 50(1) | **Providers** | design systems intended to interact directly with natural persons so those persons are informed, unless obvious |
| 50(2) | **Providers** | mark synthetic audio/image/video/text output as artificially generated, machine-readable |
| 50(3) | **Deployers** | inform natural persons exposed to emotion recognition or biometric categorisation |
| 50(4) | **Deployers** | disclose deep fakes; and disclose AI-generated text published to inform the public on matters of public interest |

Our `_ART50` carries a `provider` **and** a `deployer` entry for all four
paragraphs. Keying on the cited paragraph was the right fix; attaching both
roles to every paragraph is a second, smaller version of the original bug —
a deployer of a chatbot has no Article 50(1) duty, the provider does.

**Fix:** the obligations list carries the duty only for the role the paragraph
actually binds. Keep the counterparty line — "confirm the vendor applies
machine-readable marking" is genuinely useful — but label it as **contractual
practice**, not as an obligation. The distinction is the whole point of the
field.

Two carve-outs in 50(4) worth carrying: the law-enforcement exception, and the
reduced duty where content is part of an "evidently artistic, creative,
satirical, fictional or analogous work".

### C4. `_HIGH_RISK_PROVIDER` never cites Article 16

Article 16 — "Obligations of providers of high-risk AI systems" — is the article
that actually imposes them, and it is what Article 25 points escalated parties
to. Our list jumps straight to Arts. 9–15, 17, 43, 47–49, 72–73. Those are all
correct (titles verified), but Art. 16 is the umbrella and its absence is
conspicuous in a regulator-facing citation list.

### C5. Article 6(4) is missing — the derogation is not free

> **A provider who considers that an AI system referred to in Annex III is not
> high-risk shall document its assessment before that system is placed on the
> market or put into service. Such provider shall be subject to the registration
> obligation set out in Article 49(2). Upon request of national competent
> authorities, the provider shall provide the documentation of the assessment.**

This creates an obligations cell we do not have: **Annex III + derogation
claimed + provider** → document the assessment before placing on the market,
register under Art. 49(2), produce it on request. Claiming the derogation is a
filing, not an exit.

### C6. `_HIGH_RISK_DISTRIBUTION` merges two different articles

Confirmed distinct: **Article 23 — Obligations of importers**; **Article 24 —
Obligations of distributors**. Split the list and drop the "Art. 23/24" slash.

### C7. Article 26(11) is narrower than our line

The Act: "Without prejudice to Article 50 … deployers of high-risk AI systems
**referred to in Annex III** that **make decisions or assist in making
decisions** related to natural persons shall inform the natural persons that
they are subject to the use of the high-risk AI system." Ours drops the Annex III
limitation and the "or assist in".

### C8. Article 27 is narrower than our line

Article 27(1) applies "prior to deploying" a high-risk system referred to in
**Article 6(2)** — Annex III — "**with the exception of** high-risk AI systems
intended to be used in the area listed in **point 2 of Annex III**" (critical
infrastructure). Ours omits both the Annex III limitation and the point-2
exclusion.

### C9. GPAI systemic risk is classified by Article 51, not 55

**Article 51** — "Classification of general-purpose AI models as general-purpose
AI models with systemic risk". Art. 51(2): a model is **presumed** to have high
impact capabilities where the cumulative training compute "measured in floating
point operations is greater than 10^25". Article 55 sets the *obligations* that
follow. My prior note attributed the threshold to Art. 55; Art. 51 is correct.

---

## D. Still missing from the ladder — now verified word-for-word

### D1. Article 6(3) derogation

> By derogation from paragraph 2, an AI system referred to in Annex III shall
> not be considered to be high-risk where it does not pose a significant risk of
> harm to the health, safety or fundamental rights of natural persons, including
> by not materially influencing the outcome of decision making.

Conditions — **any one** suffices:

- (a) intended to perform a **narrow procedural task**;
- (b) intended to **improve the result of a previously completed human
  activity**;
- (c) intended to **detect decision-making patterns or deviations** from prior
  patterns and **not meant to replace or influence the previously completed
  human assessment, without proper human review**;
- (d) intended to perform a **preparatory task** to an assessment relevant to an
  Annex III use case.

And the override:

> Notwithstanding the first subparagraph, an AI system referred to in Annex III
> **shall always be considered to be high-risk where the AI system performs
> profiling of natural persons.**

The profiling override is not optional and must be checked *after* the four
limbs, not before.

### D2. Article 2 scope exclusions

Art. 2(6): the Regulation "does not apply to AI systems or AI models, including
their output, specifically developed and put into service for the **sole purpose
of scientific research and development**." Other exclusions in Art. 2 cover
military/defence/national security, third-country authorities in law-enforcement
cooperation, and purely personal non-professional use.

Our five tiers cannot express "the Act does not apply". Decide: add the outcome,
or declare Art. 2 out of Project 1 in the README.

### D3. Article 5(1)(ba) and (bb) — new prohibitions

Inserted by 2026/1744: (ba) non-consensual intimate imagery of an identifiable
natural person; (bb) the CSAM limb referencing Directive 2011/93/EU. Per
Art. 113(3)(a) as amended, these apply from **2 December 2026** — *not yet in
force*. A record hitting them today is a future prohibition, and the output
should say so rather than flattening it into "prohibited".

Also new and adjacent: **Article 4a** — processing of special categories of
personal data for bias detection and correction, with an express "this paragraph
does not create any obligation to conduct such bias detection and correction".
Relevant to the Art. 10 line in `_HIGH_RISK_PROVIDER`. And **Art. 6(1a)**,
excluding AI solely used for non-safety-related aspects of user assistance —
Annex I territory, out of our scope.

---

## E. Order of work

**Before labelling** — these change what a correct label is:

1. **Art. 6(3) derogation + profiling override** (D1) — schema field, prompt
   question, and the override applied last.
2. **Annex III 5(b) financial-fraud carve-out** (B) — prompt and a few-shot
   example. Cheapest high-value change on this list.
3. **Art. 25 escalation, correctly scoped to high-risk** (C2) — prompt question,
   asked role vs effective role.
4. **Art. 2 scope** (D2) — add the outcome or declare it out. Either is fine;
   silence is not.

**After labelling** — `obligations.py` only, no schema change:

5. Art. 4 wording and role gating (C1).
6. Art. 50 role-correct duties, practice notes labelled as practice (C3).
7. Add Art. 16 (C4); add the Art. 6(4) derogation cell (C5); split Arts. 23/24
   (C6); narrow Art. 26(11) (C7) and Art. 27 (C8); move the FLOPs threshold to
   Art. 51 (C9).
8. New prohibitions with their 2 Dec 2026 date (D3).
9. Bump `RULESET_VERSION` to name Regulation (EU) 2026/1744 and the consolidation
   date `27.07.2026`, and replace the "OPEN ITEM: sources disagree" block in
   `obligations.py` — that item is closed.

**What did not need changing:** everything in section A. The tier ladder's
shape, the Annex III citations, the Art. 26 paragraph numbers and the
post-Omnibus dates all survived contact with the text. The defects are at the
edges — scope, derogations, and which role a duty actually binds — which is
where compliance tools usually fail.
