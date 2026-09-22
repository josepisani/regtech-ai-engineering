# Day 6 — embeddings intuition, and the regulatory corpus cut along its structure

Branch `day6`. Learning target was the mechanics: dot product, cosine, structural
chunking. The corpus texts are input only; nothing here interprets them.

## Part 1 — vectors in numpy (`scratch_day6_vectors.py`, deleted before commit)

Seven steps, each with a gap to type by hand and an EXPECTED value to check
against. The three sentences to be able to say afterwards:

- The dot product multiplies two vectors position by position and adds the
  results up. It is big when both vectors are big in the same places.
- It also grows when a vector is merely longer. Multiply `cat` by 3 and its dot
  product with `dog` triples, though nothing about the meaning changed.
- Cosine is the dot product divided by both lengths. That division removes
  length and leaves direction, which is the part that carries meaning. It runs
  from -1 to 1; the shouting cat scores exactly what the quiet cat scores.

The matrix form (`M @ q`, `np.linalg.norm(M, axis=1)`) is the same arithmetic
for every row at once. That is what production retrieval runs.

Step 7, in the user's own words (2026-09-22, after six steps typed by hand):

> The dot product measures how much two vectors agree, by multiplying them
> slot by slot and adding up, so it is large when both are big in the same
> slots. Cosine similarity is the dot product divided by the product of the
> two lengths, so it only measures direction. For text search we use cosine
> because for text, how long or loud a vector is carries no meaning, only its
> direction does, and cosine ignores length by construction.

That is the "done when" for Part 1.

## Part 2 — the corpus (`data/corpus/raw/`, committed)

| File | What | Source |
|---|---|---|
| eu-ai-act.xhtml | Regulation (EU) 2024/1689, consolidated 2026-07-27 | CELEX 02024R1689-20260727 |
| dora.xhtml | Regulation (EU) 2022/2554 | CELEX 32022R2554 |
| dora-rts-ict-risk-management.xhtml | Delegated Reg. (EU) 2024/1774 | CELEX 32024R1774 |
| dora-rts-incident-classification.xhtml | Delegated Reg. (EU) 2024/1772 | CELEX 32024R1772 |
| dora-rts-ict-third-party-policy.xhtml | Delegated Reg. (EU) 2024/1773 | CELEX 32024R1773 |
| aifmd-consolidated.xhtml | Directive 2011/61/EU consolidated 2026-04-16 (includes 2024/927) | CELEX 02011L0061-20260416 |
| sfdr.xhtml | Regulation (EU) 2019/2088 consolidated 2024-01-09 | CELEX 02019R2088-20240109 |
| cssf-18-698.pdf | Circular CSSF 18/698, English | cssf.lu |
| esma-csa-compliance-internal-audit-2026.pdf | ESMA Final Report on the 2025 CSA on compliance and internal audit functions of UCITS ManCos and AIFMs (ESMA34-1436284137-2305, 11 May 2026) | esma.europa.eu |

How they were fetched: EUR-Lex answers a plain HTTP fetch with a JavaScript bot
challenge (HTTP 202, empty body), so the files come from the Publications
Office's Cellar endpoint, `publications.europa.eu/resource/celex/<id>` with
`Accept: application/xhtml+xml`. Same content, machine-readable, with the
structure marked up.

Two decisions:
- AIFMD II (Directive 2024/927) is an amending act; its Article 1 is one long
  list of edits to 2011/61/EU. The consolidated AIFMD carries the same words in
  their final place, so that is the file in the manifest.
- "Key RTS" under DORA = the three ICT-risk delegated regulations above. A
  choice, not a given; change the manifest if the plan means others.

**ESMA CSA** (2026-09-22): the plan names the series, not a document. Chosen:
the Final Report on the 2025 CSA on compliance and internal audit functions,
published 11 May 2026 — the most recent, and the one addressed to ManCos and
AIFMs under AIFMD/UCITS. The runner-up was the 2023-2024 CSA on sustainability
risks and SFDR disclosures (ESMA34-1592494965-764, 30 June 2025), which pairs
with SFDR; it is one line in the manifest away if the plan meant that one.

## Part 3 — chunking by structure (`toolkit/chunking.py`)

Units, as a lawyer would cite them: article paragraph `DORA Article 5(2)`;
whole article when unnumbered; definition or list point `AI Act Article 3,
point (1)` and `AI Act Article 5(1), point (a)` when the list is long; recital;
annex point `AI Act Annex III, point 4` when an annex is a single numbered run;
CSSF numbered point with its Part > Chapter > Section path; CSSF annex whole;
ESMA numbered paragraph `ESMA CSA 2025 para 18` under its section; ESMA annex whole.

Result: 2,775 chunks, median ~350 characters. Per document: AI Act 732, DORA
488, RTS 1774/1772/1773 177/46/42, AIFMD 511, SFDR 87, CSSF 624, ESMA 68. No
duplicate ids, nothing under 40 characters, no consolidation markers (►M1 ◄
▼B) left in, no footnote residue.

Things the run taught, each now a rule in the code:
- Two markup dialects: Official Journal originals (`oj-ti-art`, paragraphs as
  `<div id="005.002">`) and consolidated texts (`title-article-norm`,
  `span.no-parag`). Both handled; the dialect is not a parameter, the code
  tries each.
- Consolidation markers sit inside `<a>` tags and `p.modref` notes; both are
  removed before any text is read.
- Footnote links too: OJ texts write them as `<a>(29)</a>`, consolidated texts
  as `(<a>29</a>)`. 248 DORA-family chunks carried "( 29 )" inline until the
  anchors were dropped and the empty parentheses closed up.
- ESMA reports number paragraphs 1..67 and sections 1..7 in the same "N."
  style. Two counters tell them apart: a short title-case line whose number
  is the next section is a heading; a line whose number is the next paragraph
  is a paragraph. Chart axis ticks (lines of bare digits) and "Table N"
  captions are dropped; the tables were images.
- Annex II of the AI Act is a dash list (offences); AIFMD Annex I is lettered;
  AI Act Annex VIII restarts numbering per section. Splitting on those gave
  fragments and duplicate ids. Rule: split an annex only on one run 1..k.
- A list is split into points only when the unit is over 2,500 characters
  and the markers are unique; a second "(a)" list in the same unit keeps it
  whole. Short lists stay with their lead-in.
- The CSSF PDF's table of contents numbers its own entries 1, 2, 3 and looks
  like points 1-3. The body starts after the last dotted-leader line.
- CSSF headings wrap onto a second line in the PDF; the continuation is glued
  on. Points must be consecutive (1..621) to count, which is what stops
  "2013 Law" or a footnote from opening a chunk.

Known limits, left as is: CSSF point 1 is the circular's whole definitions
list (10k characters) because its entries are "1)" not "1."; pypdf splits a
few words ("othe rs", "10- 4"); the three CSSF annexes are one chunk each;
the ESMA annex (a two-column good/poor-practice table) is one chunk; a few
ESMA page-bottom footnotes ride along inside the paragraph they interrupt;
consolidated texts carry no recitals, so the AI Act, AIFMD and SFDR have none.

By-eye check (2026-09-22): an audit over all 2,775 chunks for lowercase
starts, missing end punctuation, leaked "Article N" labels, footnote tokens,
duplicates and size extremes, then twelve complete chunks read in full — one
of each unit type, including AIFMD Article 20(1) on delegation and CSSF point
516. Every boundary landed on the structure. The remaining flags are true
positives that are fine: recitals that end in a comma because the Act's
recitals are one sentence, and text that legitimately begins "Article 18 of
Regulation ...".
`chunks.jsonl` is derived and git-ignored; `python -m toolkit.chunking`
rebuilds it in about 20 s and prints the eyeball sample.

## Read-back before commit (CLAUDE.md rule)

`toolkit/chunking.py` and `toolkit/similarity.py` are committed on the `day6`
branch on 2026-09-22 so the Mac can pull them; GitHub is the only bridge
between the two machines. The five questions on each were asked on 2026-09-17
and are not yet answered, so **the read-back is still owed before `day6` is
merged to `main`**. The questions are in the session log; ask Claude to
re-post them.

## Next (from the plan, not a new plan)

Day 7: embed the chunks and retrieve with `cosine_matrix` / `top_k`; the
citation is the chunk's `ref`. The ESMA CSA file joins the manifest once named.
