# Prompt design notes

How the drafting prompt in `pipeline/draft.py` was designed, what each rule is for, and what changed after running it across models.

## The problem the prompt has to solve

A needs assessment for accredited CME is only useful if every statement can be traced to evidence. The usual LLM failure modes in this setting are:

1. A confident statement with no source.
2. A citation that does not exist, or a real PMID that points to an unrelated paper.
3. A number that drifts: a hazard ratio of 0.30 that becomes 0.35, or a median rounded the wrong way.
4. Overreach: the source shows a mouse result, and the draft writes a clinical claim.
5. Promotional tone, which is incompatible with the ACCME Standards for Integrity and Independence.

Prompt rules address the first four only partly. The design therefore pairs a constrained prompt with an independent checker (`pipeline/verify.py`) that does not use an LLM.

## Rules in the system prompt, and why

| Rule | Purpose | How it is enforced afterwards |
|---|---|---|
| Write only from SOURCES | Grounding; removes the model's background knowledge as a source | `UNKNOWN_ID` / `NONEXISTENT_PMID` |
| End every factual sentence with an exact ID, e.g. `[PMID:12345678]` | Makes every claim machine-checkable | `UNCITED` |
| Never cite an ID that is not in SOURCES; move unsupported points to "Evidence gaps" | Gives the model a legitimate place to put what it cannot support, instead of inventing a citation | `UNKNOWN_ID` |
| Copy numbers exactly | Prevents rounding and drift | `NUMBER_NOT_IN_SOURCE` |
| Report limitations and safety alongside efficacy; no promotional language | Fair balance for accredited education | Human review |

## Context design

- Each source is one block that starts with its ID, followed by title, journal, year, a design label and the abstract (truncated at 1,800 characters). The ID comes first so the model associates content with the exact string it must cite.
- Registered trials are a single line: phase, status, enrollment, interventions and primary outcomes.
- The output format is fixed: six Markdown sections. A fixed structure makes the drafts comparable across models and lets the checker treat sections differently. For example, learning objectives need no citation, and in multiple-choice questions only the rationale is checked, because the distractors are wrong on purpose.

## Iteration log

| Observation | Change |
|---|---|
| The first query set for the senolytics topic returned about a third off-topic papers (Alzheimer, cholesterol, craniopharyngioma) | Phrase-quoted the astrocyte and SASP queries and narrowed the first query to "therapy-induced / radiation-induced / temozolomide-induced senescence" |
| Several known key papers were missing | Added a dedicated query (BCL-XL, MNK inhibitor, clofoctol) and raised the per-query limit |
| The last query still contributed nothing | Found a bug: a total cap applied after concatenating queries silently dropped the last query. Results are now merged round-robin across queries |
| The checker flagged "718 patients" as unsupported | The abstract spells it "Seven hundred eighteen". Added number-word normalization |
| Multiple-choice distractors were flagged as wrong numbers | Distractors are wrong by design, so only the rationale is checked |
| ChatGPT formats gaps with labels like "Gap 1: ..." that were flagged as uncited claims | Short lines without terminal punctuation are treated as labels |

## Cross-model run (same prompt pack, 13 Oct 2026)

| Model | Checked | OK | Main issue flagged |
|---|---|---|---|
| Claude | 35 | 32 | Statements of absence ("no efficacy data in patients exist") that a search cannot prove |
| ChatGPT | 67 | 58 | Cited a trial ID found inside an abstract but outside the retrieved set; generic "educational need" sentences with weak support |
| DeepSeek | 59 | 55 | Gap statements that the cited source does not discuss directly |

No model fabricated a PMID or misquoted a number with these constraints. The remaining risk was overreach. One DeepSeek sentence claimed that current practice ignores senescence; none of its cited sources describes clinician behavior. That sentence passed the lexical check and was found on human review.

## What I would change next

- Add a rule that statements about absence must be scoped to the search ("no efficacy data were identified in the retrieved sources").
- Add a rule that claims about current clinical practice need a source that measures practice, such as a survey, audit or registry, or must move to "Evidence gaps".
- Add an optional second-model review pass that reads only the flagged sentences against their cited abstracts and proposes corrections. The non-LLM checker would still be the gate.
