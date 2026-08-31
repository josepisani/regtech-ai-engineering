# Day 2 — Structured outputs

*Concepts first. Read this before we build. ~20 minutes.*

---

## Why these four ideas, and why today

Day 1 was about what the model *is*: a thing that reads tokens and emits tokens, one at a time, with a cost attached. Today is about making that thing produce something a **program** can use rather than something a **person** has to read.

That distinction is the whole day. Prose is what a model naturally emits. Prose is useless downstream: you cannot filter a spreadsheet on a paragraph, you cannot count how often a paragraph was wrong, you cannot put a paragraph in a register that a regulator will inspect. Project 1 has to hand back a *record* — tier, flag, obligations, gaps — with the same fields every single time, so that a hundred vendor descriptions become a hundred rows.

The four ideas are the four levers that get you there.

| Idea | What it controls | In one sentence |
|---|---|---|
| Few-shot | The model's **judgement** | Show it worked examples instead of describing what you want. |
| Decomposition | The **difficulty** of each call | Ask three easy questions rather than one hard one. |
| Output schemas | The **shape** of the answer | Declare the fields up front and make the model fill a form. |
| Pydantic validation | Whether you can **trust** the shape | Check the form is filled correctly before your code touches it. |

The first two make the answer *better*. The last two make it *usable*. You need all four, and they are not interchangeable — a perfect schema around a bad judgement gives you beautifully formatted nonsense.

---

## 1. Few-shot prompting

**The term.** "Shot" means "worked example". *Zero-shot* = you describe the task and ask. *Few-shot* = you include two to five completed examples in the prompt, then give the real input.

**Why it works.** The model is a pattern-continuer. When it has seen three inputs each followed by a correctly-formed answer, producing a fourth answer of the same kind is the easiest continuation available. You are not teaching it the EU AI Act — it has read the EU AI Act. You are teaching it *your house style of answering*: how much evidence you demand before you call something high-risk, how cautious you are, what you do when the description is vague.

**The risk analogy.** This is the difference between handing a new analyst the policy manual and handing them five completed assessments from the file. The manual is authoritative and they will still get the sixth one wrong. The five completed files transmit the things the manual never wrote down — the house convention, the tolerance for ambiguity, the level of detail expected. Few-shot is showing the completed files.

**What to actually put in the examples.** This is where most people waste the technique. Do not pick your three cleanest cases. Pick:

- one **obvious** case (a CV-screening tool — high-risk, Annex III, textbook),
- one **borderline** case where you had to think, and where your reasoning is the thing worth transmitting,
- one **underspecified** case where the correct answer is *"I cannot classify this, here is what is missing."*

That third one is doing the most work in your project. It is the example that teaches the model that "insufficient information" is a permitted, respectable answer. Without it, the model will guess — not because it is lying, but because every example you showed it ended in a confident tier, so a confident tier is the pattern it continues.

**The cost.** Examples are tokens, and tokens are money and latency on every single call. Three examples of a few hundred tokens each is real overhead — this is where prompt caching earns its place on Day 3, because the examples never change between calls.

**The trap.** Examples leak. If all three of your examples are SaaS vendors, the model quietly learns "the answer is about SaaS vendors". If two of three land on high-risk, it will over-call high-risk. Your examples are a sample, and like any sample, its composition biases the estimate. Vary them deliberately.

---

## 2. Decomposition

**The idea.** Instead of one prompt that says "classify this vendor", you split the job into steps and give the model one job at a time.

For Project 1 the natural split is:

1. **Extract** — what does this description actually say? What is the system, who is the provider, what is the use, what data, who is affected, is a general-purpose model involved?
2. **Classify** — given only those extracted facts, which risk tier applies and why?
3. **Derive** — given the tier, which obligations attach?

**Why it helps.** Two reasons, and the second is the one people miss.

The obvious reason: each step is easier, so each step is more accurate. A model asked to do one thing does it better than a model asked to do four things in one breath.

The reason that matters more: **decomposition makes failure legible.** When one monolithic prompt returns the wrong tier, you have nothing to inspect — you have a wrong answer and a black box. When the split version returns the wrong tier, you can look at step 1 and see that it never noticed the system does emotion recognition in a workplace. Now you know the bug is in extraction, not in reasoning, and you know which prompt to fix. On Day 13, when you do error analysis, this is the difference between having failure *categories* and having a pile of wrong answers.

**The risk analogy.** It is why a control that fails tells you which control failed. A single end-to-end check that says "the file is wrong" is worth much less than four sequential checks where the third one lit up.

**The cost.** Three calls cost roughly three times one call, and take three times as long. That is the trade. And step 3 — deriving obligations from a tier — is *pure lookup*: once you know the tier, the obligations are a fixed list in the regulation. Do not pay a model to recite a table you can hardcode in Python. **Decomposition also means deciding which steps aren't model calls at all**, and that is often the biggest win: the hardcoded step is free, instant, and cannot hallucinate.

**Where to stop.** Do not decompose to five calls on Day 2. Start with one call and a good schema. Split only where you have *evidence* of a failure — a wrong answer you traced. Splitting speculatively is how a two-hour build becomes a two-day one.

---

## 3. Output schemas

**The term.** A schema is a written-down description of the fields an answer must have, what type each one is, and which are mandatory. "risk_tier must be one of these four strings; confidence must be a number from 0 to 1; gaps must be a list of strings; all four are required."

**How you actually get one from Claude.** You describe the schema as a **tool**. This is the piece that reads strangely at first, so here it is plainly:

The API lets you tell the model "here are some tools you may call; each tool takes arguments in this shape". A tool is normally a real function — search the web, look up a price. But nothing forces it to be. You can define a tool called `record_classification` whose arguments happen to be exactly the fields you want, and then set `tool_choice` to *force* the model to call it. The model has no choice but to emit arguments in that shape, and those arguments **are** your answer. You never execute anything. The tool is a form, and forcing the call is making the model fill it in.

Why this rather than "please reply in JSON"? Because "please reply in JSON" is a *request* and this is closer to a *constraint*. Ask politely and you get JSON wrapped in "Certainly! Here's the classification:", or JSON in a markdown code fence, or JSON with a trailing comma. The tool path gets you a parsed object from the SDK, with the field names you asked for.

**Now the honest part, and this is the sentence to remember from today:** forced tool use makes the model *aim* at your schema. Under ordinary (non-strict) tool use it does not *guarantee* it. The model can still return a tier string you never listed, a confidence of 1.5, or an empty required field. Rare, but not zero — and "rare" over a thousand records is a number, not a nuisance.

That gap between *aimed at* and *guaranteed* is precisely why the next section exists.

**The failure mode to watch for on Day 3.** If the answer runs past `max_tokens`, the JSON is cut off mid-structure and nothing parses. It looks like a mysterious schema failure and it is actually a length limit. The tell is `stop_reason` — check it, don't guess.

---

## 4. Pydantic validation

**What Pydantic is.** A Python library where you declare the shape of your data as a class, and it checks real data against that declaration — and refuses it, loudly and specifically, when it doesn't fit.

```python
from enum import Enum
from pydantic import BaseModel, Field

class RiskTier(str, Enum):
    PROHIBITED = "prohibited"
    HIGH_RISK = "high_risk"
    LIMITED_RISK = "limited_risk"
    MINIMAL_RISK = "minimal_risk"
    INSUFFICIENT_INFO = "insufficient_information"

class Classification(BaseModel):
    risk_tier: RiskTier
    is_gpai: bool
    confidence: float = Field(ge=0.0, le=1.0)   # ge/le = must be >= 0 and <= 1
    gaps: list[str]
```

Four things are happening here that matter:

1. **`RiskTier` is a closed list.** A tier of `"medium"` is not merely odd, it is *rejected*. The set of possible answers is now finite and known, which is what makes counting and eval possible later.
2. **`confidence: float` with `ge`/`le`** rejects `1.5` and rejects `"high"`. Bounds are enforced, not hoped for.
3. **Every field is required** unless you give it a default. A missing `gaps` is an error, not a silent `None` that crashes something three functions downstream.
4. **`Classification.model_json_schema()`** generates the JSON Schema — so the *same class* both defines the tool you send to the model and validates what comes back. One definition, both ends. If you add a field, both ends move together and they cannot drift apart.

**What validation buys you, precisely.** It converts a *silent* wrong shape into a *loud* one, at the boundary, before the bad data gets into your program. Without it, a missing field becomes a `None`, the `None` flows into a Streamlit table, and you find out at the demo. With it, `ValidationError` is raised at the exact line where the model's answer entered your code, and the error message names the field and the reason.

**The risk analogy.** It is the four-eyes check at the point of entry rather than at month-end reconciliation. Same error caught, but caught where it is cheap and where you can still see what caused it.

**The limit — and be clear-eyed about this.** Pydantic validates *form*, never *truth*. `risk_tier="minimal_risk"` on a CV-screening tool passes validation perfectly and is flatly wrong under Annex III. Nothing in today's toolkit catches that. That is what your hand-labelled set is for, and it is why the labelling task is not busywork: the schema is the only thing guaranteeing shape, and **your labels are the only thing that will ever measure correctness.** Days 13 and 14 are built on the set you write today.

---

## 5. Putting it together — where determinism actually comes from

Here is the argument the whole day rests on, and the reason the plan says what it says about `temperature`.

You want the same vendor description to produce the same classification, reliably, in a domain where an inconsistent answer is a defect. The instinct is `temperature=0` — collapse the sampling so the model always takes the most likely token. That instinct is now unavailable to you: Sonnet 5 returns a 400 error on `temperature`, and you cannot build a product on a parameter that may not exist on the model you deploy to.

So determinism has to come from somewhere structural. It comes from the loop:

```
call the model with the schema as a forced tool
        │
        ▼
validate the arguments with Pydantic
        │
   ┌────┴────┐
 valid    invalid
   │         │
   ▼         └──▶ call again, feeding back the exact validation error
 return              (up to N attempts, then fail honestly)
```

Read what that loop actually guarantees, because it is narrower and more valuable than it first looks:

- **It guarantees shape, not content.** Every record that leaves this function has your fields, your types, your closed list of tiers. Nothing downstream ever sees a surprise. That is a real, hard guarantee and it holds regardless of which model you point it at, whether that model supports `temperature`, and whether the provider changes its defaults next quarter.
- **The error feedback is what makes the retry worth having.** A blind retry re-rolls the dice. A retry that says *"`confidence` must be ≤ 1.0, you sent 1.5"* gives the model the specific thing to fix, and it usually fixes it. Retrying without feeding back the error is the common version of this pattern and it is much weaker.
- **The failure path must stay honest.** After N attempts, raise. Do not return a half-filled object, do not default the tier to `minimal_risk`, do not swallow it. A pipeline that silently emits a guess when the model failed is worse than one that stops, because you will never see it happen.

And this is why `insufficient_information` is a *tier in the schema* rather than an error. There are two completely different kinds of failure and they must not be confused:

- **the model failed** → validation fails → retry → eventually raise. A bug.
- **the description is inadequate** → the model succeeds, returns `insufficient_information` with the gaps listed. A finding.

The second one is the product. In your domain, "this vendor questionnaire does not tell us whether the model is used to score candidates, and we cannot classify it until it does" is a genuinely useful output — arguably more useful than a confident tier, because it is the thing a Conducting Officer can act on. Building that distinction into the schema on Day 2 is what stops the app from bluffing, and it is the same instinct as Day 8's clean refusal and Day 12's "missing data becomes a finding, never an invention". Same idea, three times, across the whole sprint.

---

## The one thing to hold onto

**Prompting makes the answer better. Schema and validation make it usable. Only your labels make it correct — and nothing you build today measures correctness.**

Keep those three separate in your head today and you will not confuse "it always returns clean JSON" with "it works". The first is the Day 2 gate. The second is Week 3.

---

*Next: the Project 1 spec — deciding what the fields actually are.*

---

## Addendum — what the docs said, written after §3 above (2026-08-31)

Section 3 says forced tool use makes the model *aim* at your schema without
guaranteeing it. That was true of the tool-use pattern the sprint plan assumed.
It is no longer the whole picture, and the check is worth recording because it
is exactly the habit §2 of START-HERE demands.

`anthropic==1.0.0` — the version in your `.venv` — has native **structured
outputs**: `client.messages.parse(..., output_format=MyModel)` sends the Pydantic
class's JSON Schema and returns `response.parsed_output` already built into an
instance of the class. Conformance is enforced during generation by a grammar,
not requested in a prompt. Verified in the installed source, not just the docs:
`resources/messages/messages.py:1113`.

Two things survive from §3 unchanged, and one gets sharper:

- **Validation and retry still earn their place**, because two documented paths
  break conformance anyway: `stop_reason == "refusal"` and
  `stop_reason == "max_tokens"`. Also because a wrapper that validates works
  against providers that have no such feature — that is the portability
  argument for `toolkit/structured.py` rather than calling `.parse()` inline.
- **The distinction between shape and truth is untouched.** A grammar can force
  `risk_tier` to be one of five strings. Nothing forces it to be the *right* one.
- **Sharper:** not every Pydantic constraint reaches the model. Reading
  `anthropic/lib/_parse/_transform.py` shows `minimum`, `maximum`, `minLength`,
  `maxLength` and `pattern` are stripped from the schema and appended to the
  field's *description* as text — a hint, not a constraint. `enum` is enforced.
  So `confidence: float = Field(ge=0, le=1)` would have *looked* enforced and
  would not have been, while `confidence: Confidence` (an enum) genuinely is.

The lesson to keep is the method, not the fact: the fact will change again by
Day 11. Read the installed library, not only the documentation — the library is
what actually runs.

---

## Handoff — end of Day 2 build session, 2026-08-31 (Mac)

**Branch:** `day2`, cut from `main` after `day1` was merged in.
**`main` is 6 commits ahead of `origin/main` and `day2` has never been pushed.**
Neither can be pushed from the assistant's sandbox (no git credentials there), so
push both by hand:

    git push origin main
    git push origin day2 -u

**Done**

- `notes/day2.md` — the four concepts, plus the addendum correcting §3 against
  the installed SDK.
- `notes/project1-spec.md` — Project 1 spec v1. Four decisions taken: five-value
  tier with `insufficient_information`, three-level confidence enum, `our_role`
  required, obligations derived in Python.
- `toolkit/structured.py` — the day's toolkit promotion. Imported by
  `src/aiact/classify.py` and by the description generator, so it has earned its
  place under the toolkit rule.
- `src/aiact/{schema,obligations,classify}.py` — the classifier core.
- `data/vendor_descriptions.jsonl` — 20 synthetic descriptions, unlabelled.
- `data/project1_labels.xlsx` — the labelling workbook (git-ignored; the
  committed artefact is `data/labels.jsonl`, once it exists).

**Gate — both items met**

1. 20/20 schema-conformant, every one on the first attempt, no truncation and no
   refusal. $0.096 total on Haiku 4.5, median 4.1s per call.
2. All four deliberately under-specified descriptions returned
   `insufficient_information` with populated gaps and `low` confidence — no
   invented tier.

Accuracy is deliberately NOT in the gate. It cannot be measured until the labels
exist, and pretending otherwise is how confident nonsense ships.

**One defect found and fixed during the first real run.** The obligations lookup
was keyed on `(tier, role)` alone, which handed a chatbot deployer the Article
50(3) emotion-recognition and 50(4) deepfake duties — neither applies to a
question-answering bot. Article 50 attaches per paragraph, not per role. The
lookup is now keyed on the paragraph the classifier cited, with an explicit
"could not be narrowed" line when no paragraph was cited. Worth remembering that
the wrong answer came from the hand-written Python, not from the model.

**Next (Day 2 remainder)**

1. Label the 20 descriptions in `data/project1_labels.xlsx`. Do it before
   looking at any model output — the predictions exist and are being held back
   deliberately.
2. Convert the sheet to `data/labels.jsonl` and commit it.
3. Then, and only then, compare. The disagreements are Day 3's edge-case tests
   and the seed of the Week 3 error analysis.

**Open item carried into Day 4:** confirm on EUR-Lex whether the Digital Omnibus
is formally adopted and published. `RULESET_VERSION` and the dates in
`obligations.py` assume the post-Omnibus timeline.
