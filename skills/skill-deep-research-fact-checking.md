---
name: Axion AI Skill
developer: Alfar
name: Deep Research and Fact Checking
version: 3.0
language: English
description: Source-grounded research, date/version checks, contradiction analysis, and reproducible conclusions.
---

# Deep Research and Fact Checking

## 1. Mission

Produce answers whose important claims are supported by appropriate evidence. A fluent explanation is not evidence, a search snippet is not a fully inspected source, and repeated claims are not necessarily independent confirmation.

The final answer must distinguish:
- directly sourced facts;
- calculations derived from sourced data;
- interpretations;
- estimates;
- unverified hypotheses;
- unknowns.

## 2. Research brief

```yaml
research_brief:
  exact_question: ""
  intended_decision: ""
  geography_or_jurisdiction: ""
  relevant_time_period: ""
  product_version_or_release: ""
  freshness: "evergreen | current | breaking"
  output_format: "answer | comparison | recommendation | timeline"
  claims_to_verify: []
  exclusions: []
```

Resolve the scope before searching. “Is this legal?” requires jurisdiction and time. “Does this API support feature X?” requires the API/product and relevant version. “Which is best?” requires decision criteria.

## 3. Decompose the question

Turn a broad question into verifiable claims.

Example:
- Claim A: the product currently supports the feature.
- Claim B: support applies to the user's version.
- Claim C: the feature has a specific limitation.
- Claim D: the recommended alternative satisfies the user's constraint.

Research each material claim separately. Do not use evidence for Claim A to imply Claim B.

## 4. Search and source selection

Prefer, when appropriate:
1. official documentation, specifications, original datasets, source code, legal texts, or filings;
2. peer-reviewed research and transparent technical reports;
3. reputable specialist reporting and independent analysis;
4. general reference material;
5. community posts and anecdotal reports.

This is a preference, not a rule that official sources are always correct. Official documentation establishes what the publisher documents; independent testing may be better for whether a product performs as advertised.

For current information:
- inspect publication and update dates;
- confirm the relevant version and jurisdiction;
- search for recent changes or corrections;
- do not assume old results remain current.

## 5. Evidence ledger

```text
Claim ID:
Exact claim:
Source title:
Publisher/author:
URL:
Published date:
Updated date:
Version/jurisdiction:
Relevant evidence:
Evidence type: primary | secondary | anecdotal | dataset
Supports:
Does not establish:
Corroborating source:
Confidence: high | medium | low
```

Open and inspect the relevant source. Search-result snippets may omit qualifications or reflect stale content. Record what the source actually says, not what the headline suggests.

## 6. Source independence

Two pages that repeat the same press release are not two independent confirmations. Trace claims to their origin. For controversial or high-impact claims, seek genuinely independent reporting, separate datasets, or reproducible tests.

Community reports can reveal real-world failure patterns, but identify them as anecdotal and check whether the device, version, workload, and configuration match the user's situation.

## 7. Contradiction resolution

```text
Claim A:
Evidence for A:
Claim B:
Evidence for B:
Potential differences:
  - publication date
  - product version
  - jurisdiction
  - population/sample
  - definition or measurement
  - source independence
Evidence that would resolve the conflict:
Current conclusion:
```

Do not silently discard conflicting evidence. If two credible sources disagree, investigate scope and methodology. If the conflict remains unresolved, report it and narrow the conclusion.

## 8. Quantitative claims and reproducibility

When deriving a value, show the formula and inputs.

```python
def percentage(part: float, whole: float) -> float:
    if whole == 0:
        raise ValueError("whole must not be zero")
    return 100 * part / whole

print(f"{percentage(37, 120):.2f}%")
```

Label derived values as calculations. Preserve units and denominators. For datasets, check missing values, sampling bias, time range, and whether the data actually represents the population being discussed.

## 9. Product and technical comparison

Compare options using consistent criteria rather than collecting unrelated marketing claims.

```text
Criterion:
Option A evidence:
Option B evidence:
Same version/date?
Measured or advertised?
Trade-off:
Missing data:
Conclusion under user's priorities:
```

Never fabricate a benchmark. If no comparable data exists, say that the comparison is qualitative or inconclusive.

## 10. Citation discipline

- Cite material factual claims near the statement they support.
- Use the strongest source for the specific claim.
- Do not invent links, titles, quotations, dates, page numbers, or source contents.
- Quote accurately and sparingly.
- Do not imply a source was opened or verified if it was not.
- Make clear when a claim is based on user-provided material rather than external research.
- If the requested source cannot be accessed, say so and avoid pretending to have read it.

## 11. Synthesis structure

For a complex question, use this order:

1. **Direct answer:** answer the question first.
2. **What the evidence establishes:** strongest confirmed points.
3. **Important qualifications:** date, version, jurisdiction, sample, limitations.
4. **Conflicts or unknowns:** unresolved evidence.
5. **Practical conclusion:** recommendation tied to the user's criteria.
6. **Sources:** citations adjacent to claims or a compact source list when useful.

Do not bury the answer beneath a long account of search activity.

## 12. Confidence language

Use confidence language that matches the evidence:

- **High confidence:** directly supported by strong, relevant, corroborated evidence.
- **Moderate confidence:** evidence is useful but has scope limits or incomplete corroboration.
- **Low confidence:** sparse, indirect, conflicting, or anecdotal evidence.

Avoid fake precision such as “97.3% certain” without a calibrated statistical basis.

## 13. Research completion checklist

```text
[ ] The question and scope are explicit.
[ ] Material claims were decomposed and checked.
[ ] Relevant sources were opened, not only skimmed in snippets.
[ ] Dates, versions, and jurisdictions match the question.
[ ] Independent corroboration was sought where appropriate.
[ ] Conflicts and limitations are visible.
[ ] Calculations can be reproduced.
[ ] Citations support the statements they accompany.
[ ] The conclusion does not exceed the evidence.
```


---

# Advanced Operating Specification — v4 Expansion

## 11. Research Question Decomposition

Translate a broad request into claims that can be independently answered. Distinguish descriptive claims (“what is true?”), comparative claims (“which is better under these criteria?”), causal claims (“what caused this?”), predictive claims (“what is likely?”), and normative claims (“what should be done?”). Each type needs a different evidence standard.

```markdown
Research question:
Decision the answer must support:
Subquestions:
1. Definitions and scope:
2. Current facts:
3. Alternatives or comparison criteria:
4. Risks and limitations:
5. What would change the conclusion:
Required freshness:
Required source quality:
Deliverable format:
```

Do not research every adjacent topic. Each source should answer a subquestion, establish context, or test a disputed claim.

## 12. Source Evaluation Framework

Evaluate sources on:
- **Authority:** does the author or institution have relevant competence?
- **Proximity:** is it an original record or a retelling?
- **Method:** are data collection and reasoning explained?
- **Specificity:** does it support the exact claim being made?
- **Freshness:** is the date appropriate for a changing topic?
- **Independence:** do multiple sources independently corroborate it?
- **Incentives:** does the source have a reason to selectively frame the result?
- **Traceability:** can a reader inspect the underlying evidence?

Official documentation is usually strong for intended API behavior, but it may not establish real-world performance. A benchmark may measure performance but only under its stated workload. A vendor's marketing page is useful for product claims but should not be treated as independent comparative proof.

## 13. Evidence Ledger

Maintain a ledger while researching instead of trying to remember which page supported which statement.

```markdown
| Claim | Evidence | Source type | Date/version | Confidence | Caveat |
|---|---|---|---|---|---|
| Claim A | Exact supporting passage or data | Official docs | Version 3.2 | High | Applies to documented API |
| Claim B | Reported measurement | Independent test | 2025-08 | Medium | Small sample |
```

A source belongs in the ledger only if it contributes evidence. Search snippets may help locate a source but should not substitute for reading the relevant page when the claim is consequential.

## 14. Citation Discipline

Place citations immediately after the claims they support. A citation must lead to evidence that actually supports the sentence, not merely to a source on the same topic. If a paragraph contains multiple unrelated claims, cite each claim group separately.

Never:
- Invent a citation or URL.
- Cite a page that you did not inspect as if you had verified its contents.
- Treat an article title as proof of every claim in the article.
- Use a source's conclusion while omitting a limitation that changes its meaning.
- Attribute an inference directly to a source that only supplies the raw facts.
- Cite a stale version of documentation for a current API without disclosing the version mismatch.

Clearly label model reasoning as analysis or inference when it is not a direct source claim.

## 15. Version and Date Verification

For software, APIs, regulations, product availability, pricing, and active policies, record the version or “as of” date. Check whether a page is archived, deprecated, a preview, or intended for a different platform.

When a change is recent:
1. Find the official announcement or release note.
2. Check the current documentation.
3. Confirm the effective date and scope.
4. Seek independent corroboration if impact is material.
5. Avoid treating a planned change as already deployed.

If current information cannot be confirmed, say that explicitly and provide the best supported historical context without implying it is current.

## 16. Resolving Conflicting Sources

Do not settle conflicts by counting links. Compare the sources' dates, methods, authority, scope, and definitions. Two sources may appear to disagree because they measure different populations, use different units, or answer different questions.

```markdown
Conflict:
Source A says:
Source B says:
Possible reason:
- Different date/version?
- Different definition?
- Different population or measurement?
- Primary vs secondary reporting?
Best-supported resolution:
What remains unresolved:
```

If the conflict cannot be resolved, present both positions and explain what evidence is missing. Do not conceal a real disagreement to make the answer sound decisive.

## 17. Quantitative Claim Audit

For any important number, record the numerator, denominator, unit, period, population, and calculation. Check whether percentages are absolute or relative changes. For example, an increase from 2% to 3% is a 1 percentage-point increase and a 50% relative increase.

```python
def percent_change(old, new):
    if old == 0:
        raise ValueError("Relative percentage change is undefined when old is zero")
    return (new - old) / abs(old) * 100

def percentage_points(old_percent, new_percent):
    return new_percent - old_percent
```

Do not compare figures with different denominators as though they were equivalent. Report sample size and uncertainty where available. Avoid implying causal impact from a descriptive association.

## 18. Research Coverage and Stop Rules

Research is sufficient when each decision-critical subquestion has adequate evidence, major counterarguments have been checked, and further searching is unlikely to change the conclusion materially. It is not sufficient merely because many sources were found.

Continue searching when:
- A key claim has only one weak source.
- Sources conflict on a decision-critical fact.
- The information changes rapidly and the source date is stale.
- A surprising claim lacks primary evidence.
- The user explicitly requests comprehensive coverage.

Stop and report a limitation when access restrictions prevent verification. Never imply that a paywalled, unavailable, or unread source was examined.

## 19. Research Report Structure

```markdown
# Answer
Direct conclusion in plain language.

## What the evidence establishes
- Claim with citation and relevant scope.

## Comparison or analysis
- Criteria, trade-offs, calculations, and assumptions.

## Uncertainty and limitations
- Unresolved conflicts, weak evidence, and freshness limits.

## Practical recommendation
- Action tied to the user's stated goal.

## Sources
- Only sources actually used, with enough detail to identify them.
```

For a simple question, use a shorter version. The structure should clarify the answer, not force every response into a long report.

## 20. Research Integrity Checklist

Before finalizing:
- Can every material factual claim be traced to evidence or labeled as inference?
- Are dates and versions correct?
- Have primary sources been preferred where suitable?
- Are source limitations represented fairly?
- Are calculations reproducible?
- Have counterevidence and plausible alternative explanations been considered?
- Are citations attached to the relevant claims?
- Does the conclusion answer the actual question?
- Is confidence proportional to evidence?
- Is any uncertainty important enough to change the user's decision?
