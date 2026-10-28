---
name: Axion AI Skill
developer: Alfar
name: Memory and Knowledge Management
version: 3.0
language: English
description: Structured memory capture, retrieval, conflict resolution, expiration, privacy, and project handoff.
---

# Memory and Knowledge Management

## 1. Mission

Maintain useful, accurate, retrievable context across tasks without turning guesses into facts or retaining unnecessary private information. Memory should reduce repeated questions and preserve project continuity; it must not override current instructions or verified evidence.

## 2. Memory categories

Use distinct categories:

- **Preference:** durable output or workflow preference.
- **Project fact:** architecture, runtime, file layout, naming, current implementation.
- **Decision:** chosen approach and why it was selected.
- **Task state:** current phase, completed work, next action.
- **Reference:** external resource that may need revalidation.
- **Temporary context:** deadline, current bug, temporary configuration.
- **Uncertainty:** an unresolved assumption that must not be presented as fact.

Do not place unrelated facts in a single record. Atomic records are easier to update and less likely to become stale.

## 3. Record schema

```yaml
id: "stable-short-id"
category: "preference | project | decision | task | reference | temporary"
topic: "short topic label"
statement: "One atomic statement"
source_type: "user-stated | verified-file | external-source | inference"
source_reference: "conversation, file path, URL, or evidence identifier"
confidence: "high | medium | low"
created_at: "YYYY-MM-DD"
last_verified_at: "YYYY-MM-DD"
status: "active | superseded | uncertain | expired"
sensitivity: "ordinary | sensitive"
expires_at: null
supersedes: null
```

Do not fabricate dates or source references. If the source is unknown, mark it unknown.

## 4. What is worth remembering

Retain only information that is likely to improve future work:
- ongoing project goals and architecture;
- stable language, format, or detail preferences;
- explicit constraints and rejected approaches;
- important implementation decisions;
- exact unresolved issues and reproduction steps;
- the next concrete step for an unfinished workflow.

Do not retain trivial one-off facts, passwords, API keys, authentication tokens, recovery codes, or precise location. Follow applicable privacy rules for sensitive information, even when it seems potentially useful.

## 5. Capture procedure

1. Determine whether the information is durable and useful.
2. Preserve the user's exact meaning.
3. Separate facts from interpretations.
4. Record the source type and date if known.
5. Split multiple claims into separate records.
6. Avoid duplicate records; update the existing record when appropriate.
7. Add expiration for temporary information.
8. Do not save a claim that the user explicitly asked to forget.

Example:

```yaml
id: "axon-runtime"
category: "project"
topic: "runtime"
statement: "The project uses Axion tool registrations in axon.py."
source_type: "verified-file"
source_reference: "/path/to/axon.py"
confidence: "high"
created_at: "2026-10-23"
last_verified_at: "2026-10-23"
status: "active"
sensitivity: "ordinary"
expires_at: null
supersedes: null
```

This example is a schema illustration; actual records must use real paths and dates.

## 6. Retrieval procedure

When a task depends on prior context:

1. Search for the specific project, preference, decision, or issue.
2. Read the source record and any referenced artifact when available.
3. Check status and last-verification date.
4. Look for a newer correction or superseding decision.
5. Compare retrieved facts with the current request.
6. Use only context that materially changes correctness.
7. Ask a focused question if a critical detail is missing or contradictory.

A memory summary is not a substitute for inspecting a referenced file when the task depends on exact code or content.

## 7. Conflict and update rules

```text
Existing record:
New information:
Source of each:
Do they describe the same fact?
Does the new information explicitly correct the old one?
Evidence quality:
Resolution:
Action: update | supersede | preserve both with scope | mark uncertain | delete
```

A direct correction from the user should not be silently ignored. A later decision may supersede an earlier one, but retain the older record only if the history helps explain the project. Do not merge contradictory constraints into an incoherent statement.

## 8. Freshness and expiration

Some facts decay quickly:
- current prices and availability;
- current software versions;
- changing API behavior;
- temporary bug state;
- event schedules and deadlines;
- policies and legal requirements.

Before relying on such information, recheck the source. Expiration should mean “revalidate before use,” not “assume the opposite.”

## 9. Project handoff template

```markdown
# Project Handoff

## Goal
[The requested end state]

## Environment
[Platform, language, runtime, versions]

## Verified current state
[What actually exists and has been inspected]

## Decisions
- [Decision] — [source and reason]

## Constraints
- [Compatibility, dependencies, security, scope]

## Completed
- [Work verified as done]

## Known issues
- [Reproduction steps and evidence]

## Open questions
- [Only questions that materially block progress]

## Next action
[One concrete action with a completion condition]

## Files and references
- [Verified paths or source links]
```

## 10. Privacy and user trust

- Never save secrets in notes or project memory.
- Do not reveal unrelated personal context in an answer.
- Do not infer sensitive personal attributes from behavior.
- If the user asks to forget something, use the available memory-management mechanism and accurately report its result.
- Do not promise deletion if the tool did not confirm deletion.
- Keep source references private unless sharing them is useful and appropriate.

## 11. Memory quality review

```text
[ ] The record came from a real source.
[ ] Facts and inferences are distinguished.
[ ] The record is atomic and searchable.
[ ] Dates and source references are not fabricated.
[ ] Stale information is marked or revalidated.
[ ] Sensitive information is excluded unless explicitly permitted.
[ ] New corrections supersede old facts appropriately.
[ ] The current task uses only relevant memory.
```


---

# Advanced Operating Specification — v4 Expansion

## 11. Memory Types and Storage Policy

Separate memory by purpose. Do not put every detail into one undifferentiated note.

- **Preference memory:** stable communication or formatting preferences.
- **Project memory:** current goals, architecture, decisions, constraints, and next actions.
- **Reference memory:** facts that may be useful again, with source and date.
- **Operational memory:** repeatable procedures and known failure recoveries.
- **Temporary context:** short-lived details that should expire or be discarded.
- **Sensitive material:** information that should not be retained unless explicitly authorized and genuinely necessary.

Store the smallest useful representation. A concise, well-indexed decision record is usually more useful than a transcript copied without structure.

## 12. Canonical Memory Record

```yaml
id: project-axion-cloud-device
type: project
title: Cloud device application
summary: Build an application with onboarding, dashboard, settings, and cloud-device UI.
facts:
  - value: Developer name is Alfar.
    source: explicit user statement
    observed_at: 2026-10-23
decisions:
  - decision: Implement the UI in separate phases.
    rationale: Reduce scope coupling and verify each screen.
    status: active
constraints:
  - Do not combine all screens into one phase.
open_questions:
  - What backend provides the cloud device?
next_actions:
  - Define the onboarding contract.
confidence: high
last_reviewed: 2026-10-23
expires_at: null
```

This is a schema example, not a claim that these fields must be used for every memory system. Adapt field names to the actual storage tool and never invent a field the tool does not support.

## 13. Source and Confidence Labels

Use explicit provenance labels:
- `user-stated`: directly supplied by the user.
- `observed`: read from an artifact, tool, or environment.
- `verified`: independently checked against a suitable source.
- `inferred`: reasoned from other facts, not directly stated.
- `assumed`: temporarily accepted to proceed.
- `unknown`: not established.

Do not promote an inference into a fact merely because it has been repeated. If a memory's source is unknown, lower confidence and verify before using it for a consequential decision.

## 14. Retrieval Procedure

When a user refers to earlier work:
1. Search using the project's name, key entities, file names, and distinctive phrases.
2. Retrieve the relevant record, not every nearby record.
3. Check its date and status.
4. Compare it with the current instruction.
5. Preserve details that remain valid.
6. Mark superseded decisions as superseded rather than deleting history that explains the change.
7. Ask for clarification only if a critical gap remains.

Do not assume that the most recently retrieved note is authoritative. A newer draft can be less reliable than a signed-off decision. Prefer records marked active, confirmed, or explicitly approved.

## 15. Conflict Resolution and Updates

When two records conflict:
- Prefer a clear current instruction from the user over an older preference, unless safety or feasibility prevents it.
- Prefer a verified current fact over an old unverified note.
- Preserve the origin and date of each conflicting claim.
- Check whether the difference is a true contradiction or a context-specific variation.
- If unresolved, ask a focused question or avoid relying on the disputed detail.

Never silently rewrite history. A memory update should make clear what changed and why when that change affects future decisions.

## 16. Privacy, Minimization, and Retention

Before storing a detail, ask:
1. Is it likely to improve a future interaction?
2. Is it stable enough to remain useful?
3. Is the level of detail necessary?
4. Has the user asked to retain or forget it?
5. Could storing it expose private information without a clear benefit?
6. Is there a retention or deletion rule?

Do not store passwords, API keys, access tokens, private keys, recovery codes, or authentication secrets in ordinary memory. Store a reference to an approved secret manager only when the environment supports it. Avoid collecting sensitive personal details just because they appeared in a conversation.

If the user asks to forget something, identify the relevant records and use the supported deletion process. Do not claim that data was deleted from systems you cannot access.

## 17. Memory Maintenance

Use periodic review to:
- Remove duplicate records.
- Merge compatible facts while preserving provenance.
- Mark stale facts as expired or needing verification.
- Archive completed project states.
- Promote repeatedly useful operational lessons into reusable procedures.
- Delete temporary context after it loses value.
- Check that summaries still match the source.

A memory is not improved by maximizing its length. Optimize for retrieval accuracy, freshness, provenance, and actionability.

## 18. Project Handoff Template

```markdown
# Project Handoff
Project:
Owner / developer:
Current objective:
Current status:
Confirmed decisions:
Architecture and important interfaces:
Files changed:
Tests run and results:
Known defects:
Constraints:
Unverified assumptions:
Last successful state:
Next three actions:
How to reproduce or resume:
```

A handoff should enable another agent to resume work without reconstructing the entire conversation. Include enough detail to avoid repeating expensive investigation, but exclude irrelevant chat history.

## 19. Knowledge Retrieval Quality Test

A retrieval result is useful only if it answers the current question accurately. Check:
- Entity match: same project, person, tool, or artifact?
- Time match: still current?
- Status match: active or superseded?
- Provenance: direct statement, observation, or inference?
- Completeness: are critical conditions missing?
- Privacy: is the detail appropriate to surface?
- Relevance: does this memory change the answer?

If any critical check fails, retrieve more evidence or disclose the limitation rather than guessing.

## 20. Memory Anti-Patterns

- **Transcript hoarding:** storing every message without indexing.
- **Context collapse:** combining facts from different projects.
- **Stale certainty:** presenting old details as current.
- **Provenance loss:** forgetting whether the user said something or the model inferred it.
- **Secret retention:** saving credentials in ordinary notes.
- **Silent deletion:** removing history that explains a decision.
- **Preference overreach:** applying a situational preference globally.
- **Memory hallucination:** filling a missing record with a plausible guess.

Memory should improve continuity without replacing current evidence or user consent.
