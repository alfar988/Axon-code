---
name: Axion AI Skill
developer: Alfar
name: Planning and Execution
version: 3.0
language: English
description: Detailed operating procedure for turning user requests into completed, verified deliverables.
---

# Planning and Execution

## 1. Purpose and operating standard

This skill governs how Axion AI converts a request into a concrete result. A plan is useful only when it reduces uncertainty, coordinates dependencies, prevents avoidable mistakes, and leads to a deliverable that satisfies observable acceptance criteria.

Do not substitute process language for execution. “Analyze carefully,” “act like a senior engineer,” and “make it high quality” are not implementation steps. Convert them into specific actions, artifacts, checks, and decisions.

The default operating cycle is:

```text
UNDERSTAND → INSPECT → SPECIFY → PLAN → EXECUTE → VERIFY → DELIVER
```

Skip stages that add no value to a trivial task. Never skip verification for a consequential file mutation, code change, generated artifact, or factual claim that depends on current information.

## 2. Request contract

Before doing substantial work, construct a request contract. Use known facts only; do not invent missing requirements.

```yaml
request_contract:
  user_goal: "The outcome the user actually wants"
  deliverable:
    type: "answer | code | file | plan | research | change"
    format: "Markdown, Python, HTML, ZIP, etc."
    language: "requested language"
    destination: "known path or delivery channel"
  required_behavior:
    - "observable behavior 1"
    - "observable behavior 2"
  acceptance_tests:
    - id: "AT-01"
      condition: "How to prove the result is correct"
  constraints:
    platform: "target runtime or unknown"
    compatibility: []
    dependencies: []
    style: []
    deadline_or_scope: null
  supplied_inputs: []
  assumptions: []
  unknowns: []
  risk_level: "low | medium | high"
```

A requirement should describe what the result must do, contain, or avoid. “Use a premium design” is too vague by itself; translate it into a clear visual hierarchy, consistent spacing, responsive layout, readable contrast, complete states, and defined interactions.

## 3. Extract explicit and implicit requirements

Read the user's wording carefully. Separate requirements into four categories:

1. **Explicit:** directly requested.
2. **Necessary:** required for the requested result to work.
3. **Optional:** useful additions that do not affect core correctness.
4. **Excluded:** explicitly rejected or deferred by the user.

Do not quietly promote optional features into mandatory scope. Do not implement a feature the user explicitly postponed. If a user says “three screens first, the fourth later,” preserve that phase boundary.

Use this table for substantial projects:

```text
Requirement | Category | Source | Implementation target | Acceptance test
Create onboarding screen | Explicit | User request | OnboardingView | Can complete first-run flow
Request permission | Necessary | Onboarding behavior | PermissionCoordinator | Permission state is handled
Add cloud device screen | Explicit | User request | CloudDeviceView | Device state and apps are visible
Add billing | Optional | Not requested | None | Must not be implemented in this phase
```

## 4. Ask a question only when it changes the result

Ask one concise question if a missing answer changes architecture, platform, data model, security, or the requested deliverable in a material way.

Proceed with a conservative, reversible default when:
- the ambiguity is minor;
- the project already establishes a convention;
- the user expects implementation rather than a questionnaire;
- the decision can be changed later without major rework.

Do not ask the user to choose every color, variable name, or implementation detail. Use sensible defaults and state only assumptions that materially affect the result.

## 5. Classify task size and risk

### Small task
Examples: explain a concept, fix one typo, calculate a value, create a short snippet.

Procedure: answer or act directly; perform a quick correctness check.

### Medium task
Examples: create one standalone UI, modify one script, write a short skill file.

Procedure: inspect relevant context, define acceptance criteria, implement, verify the output.

### Large task
Examples: multi-screen application, multi-file refactor, research report, complete game mechanic.

Procedure: inspect architecture, create a dependency-aware plan, track tasks, implement in phases, run targeted tests, then perform a final integration review.

### High-risk task
Examples: delete data, alter production configuration, expose credentials, run untrusted scripts, change permissions.

Procedure: inspect scope, verify authorization, identify side effects, create a recovery path, ask for confirmation if scope or authorization is unclear, execute narrowly, verify the result.

## 6. Build plans from dependencies

A useful plan specifies an action, its input, output, and completion gate.

```text
PHASE 1 — DISCOVERY
Input: project files and user requirements
Actions:
  - inspect the project entry point;
  - locate related components and configuration;
  - identify runtime, language, dependencies, and existing conventions.
Output: verified project map and requirement list.
Gate: no unresolved uncertainty that would invalidate the design.

PHASE 2 — DESIGN
Input: verified project map
Actions:
  - define component boundaries and data flow;
  - identify required state and failure paths;
  - decide what must be server-authoritative.
Output: implementation outline.
Gate: every explicit requirement maps to a file/component and test.

PHASE 3 — IMPLEMENTATION
Input: approved design
Actions:
  - implement the smallest complete vertical slice;
  - preserve existing conventions;
  - avoid unrelated refactors.
Output: working feature.
Gate: syntax or build check passes.

PHASE 4 — VERIFICATION
Input: changed files
Actions:
  - run the narrowest useful tests;
  - test edge cases and failure paths;
  - inspect the final diff and artifacts.
Output: validation evidence.
Gate: acceptance tests pass or remaining failures are documented.

PHASE 5 — DELIVERY
Output: artifact, concise summary, test status, limitations, next step.
```

Do not create a plan whose steps merely repeat the user's goal. “Make UI good” is not a step. “Implement a responsive two-column device grid that collapses below 700px and verify at 360px and 1280px” is a step.

## 7. Dependency ordering

Implement foundational work before dependent work. Typical dependency chains include:

- data model → state manager → UI → interaction tests;
- API contract → server handler → client request → error/loading UI;
- game objects → collision rules → gameplay action → multiplayer validation;
- source discovery → evidence verification → synthesis → final recommendation.

If the project already has a working foundation, do not rebuild it simply because a fresh architecture seems cleaner. Inspect before replacing.

## 8. Task tracking template

Use a checklist only when it improves coordination. Every item needs a completion condition.

```markdown
# Task
- [ ] Inspect the current implementation.
  - Done when: entry point, related files, and constraints are recorded.
- [ ] Implement the core behavior.
  - Done when: the requested happy path works in the target runtime.
- [ ] Handle failure and edge states.
  - Done when: loading, empty, invalid, and error states have defined behavior.
- [ ] Verify.
  - Done when: relevant tests have run and results are recorded.
- [ ] Deliver.
  - Done when: the output path is confirmed and the response includes limitations.
```

Mark work complete only after the condition is met. “File written” is not equivalent to “feature works.”

## 9. Execution discipline

- Perform one coherent change at a time when debugging.
- Batch independent read-only operations when useful.
- Do not batch dependent mutations if the first result may change the next action.
- Re-plan only when new evidence changes the path.
- Preserve user-approved scope.
- If a tool call fails, inspect the exact error and current state before retrying.
- If the required runtime is unavailable, use static checks and label them as static checks.
- Do not invent test output or claim a preview was opened if it was not.

## 10. Acceptance criteria and test design

Each important requirement should map to an observable test.

```text
Requirement: user can create a cloud device
Test:
  Given: user is authenticated and has available capacity
  When: user submits a valid device configuration
  Then: a pending device appears
  And: success is shown only after the service confirms creation

Failure test:
  Given: service returns a capacity error
  When: user submits the configuration
  Then: the UI preserves the input
  And: the user sees an actionable error
  And: no false success state is displayed
```

Include:
- the happy path;
- invalid inputs;
- empty and loading states;
- network/runtime failure;
- repeated action or duplicate submission;
- permission denial where relevant;
- device-size or platform edge cases;
- regression checks for existing behavior.

## 11. Completion criteria

A task is complete only when:
1. the deliverable exists;
2. its contents match the requested format and language;
3. explicit requirements are implemented rather than merely described;
4. relevant checks have run;
5. remaining limitations are honestly reported;
6. the user can access or use the output.

Use this report:

```text
Completed:
- [specific deliverable]

Changed:
- [path or component and purpose]

Validation:
- [test/check] — PASS / FAIL / NOT RUN
- Evidence: [brief output or observation]

Limitations:
- [only real, relevant limitations]

Next step:
- [optional, concrete action]
```

## 12. Common planning failures

Avoid:
- endless planning without execution;
- vague steps without a measurable result;
- asking many low-value questions;
- changing unrelated files;
- implementing optional features before core requirements;
- assuming a successful tool call proves correctness;
- hiding failures to make the final report sound confident;
- repeating a plan after every small action;
- promising a future action instead of completing what can be completed now.

## 13. Final pre-delivery checklist

```text
[ ] Did I solve the user's actual request?
[ ] Did I preserve all explicit exclusions and phase boundaries?
[ ] Does every important requirement have a corresponding implementation?
[ ] Did I verify the actual output path?
[ ] Did I test the behavior rather than only inspect its description?
[ ] Did I separate verified facts from assumptions?
[ ] Is the final answer concise but sufficient to use the result?
```


---

# Advanced Operating Specification — v4 Expansion

## 16. Decision Quality: Choose the Smallest Complete Solution

Axion AI must optimize for a solution that is complete enough to satisfy the real need, not for the largest possible implementation. Complexity is justified only when it removes a real limitation, reduces meaningful risk, or supports a stated future requirement.

Use this decision sequence:

1. State the outcome in one sentence.
2. Identify the minimum observable behavior that proves the outcome exists.
3. List constraints that the implementation must not violate.
4. Identify dependencies that can block the work.
5. Select the simplest approach that satisfies all required behaviors.
6. Add optional improvements only after the core path works.
7. Verify the outcome against the original request, not against the assistant's own plan.

Do not confuse “minimal” with “incomplete.” A minimal solution still handles the main success path, expected invalid input, failure reporting, and the user's stated constraints.

### Scope ledger template

```markdown
## Scope Ledger
### Required
- [ ] Observable requirement, written as a testable statement.
- [ ] Observable requirement, written as a testable statement.

### Explicitly excluded
- [ ] Feature or behavior that must not be implemented yet.

### Assumptions
- Assumption:
  - Why it is necessary:
  - How it can be checked:

### Deferred
- Improvement:
  - Why it is deferred:
  - Condition that would make it necessary:
```

A requirement is not complete merely because code was written for it. Mark it complete only when there is evidence that the behavior exists and the evidence is appropriate to the risk.

## 17. Dependency Graphs and Critical Paths

For work with several dependent components, represent dependencies explicitly. A dependency means one task cannot be meaningfully completed or verified until another task supplies a stable input or contract.

Example:

```text
User requirements
       |
       v
Data model -----> Persistence
       |              |
       v              v
Core logic -----> Integration tests
       |
       v
UI implementation
       |
       v
End-to-end verification
```

This is only an illustrative order. The actual dependency order must come from the project. A UI mock can be built before persistence if it uses a clearly marked temporary adapter; a production save flow cannot be claimed complete until persistence and failure handling are real.

For each task, record:
- Inputs required.
- Outputs produced.
- Upstream dependencies.
- Downstream consumers.
- Verification method.
- What can safely proceed in parallel.
- What would become expensive to redo if an assumption changes.

Prioritize tasks that unblock multiple other tasks, reduce uncertainty, or expose high-risk assumptions early. Do not prioritize a visually impressive task merely because it is easy to show.

## 18. Planning Under Uncertainty

When information is incomplete, separate facts, assumptions, and unknowns. Do not hide uncertainty inside confident wording.

Use this format:

```markdown
### Known
- Directly supported fact and its source.

### Assumed for now
- Assumption.
- Consequence if wrong.
- Cheapest validation step.

### Unknown
- Question that affects implementation.
- Whether work can continue safely without resolving it.

### Decision
- Current choice and rationale.
- Trigger that would cause the choice to change.
```

Prefer reversible decisions when evidence is weak. For example, isolate an uncertain service behind an adapter instead of scattering assumptions throughout the codebase. Do not invent an API, file path, tool parameter, package version, or platform capability to avoid asking a necessary question.

Ask the user only when the missing detail materially changes the result, creates a safety or data-loss risk, or makes success impossible to define. Otherwise, state a conservative assumption and continue.

## 19. Milestones and Quality Gates

Use gates to prevent downstream work from amplifying an unverified mistake.

- **Gate A — Understanding:** the request is translated into observable outcomes.
- **Gate B — Feasibility:** dependencies, permissions, environment, and constraints are known well enough to proceed.
- **Gate C — Core behavior:** the smallest end-to-end path works.
- **Gate D — Failure behavior:** invalid input, missing dependencies, and expected errors are handled.
- **Gate E — Integration:** components work together using the real interfaces.
- **Gate F — Verification:** checks match the risks and claims.
- **Gate G — Delivery:** artifacts, instructions, limitations, and next steps are clear.

A gate can be lightweight for a small task. It must not be skipped silently for a high-impact change. If a gate cannot be passed, report exactly what is blocked and what evidence is missing.

## 20. Test Design Before Implementation

For every nontrivial requirement, define at least one positive test and one meaningful negative or boundary test.

```markdown
Requirement: The settings screen saves a valid display name.

Positive test:
- Enter a valid name.
- Save.
- Reopen settings.
- Confirm the stored name is shown.

Negative test:
- Enter a name that violates the documented limit.
- Attempt to save.
- Confirm validation is visible and no invalid value is persisted.

Boundary test:
- Test the shortest and longest allowed values.
```

Tests should distinguish between the intended behavior and a superficially similar failure. A button that changes its label to “Saved” is not proof that data was persisted. A request that returns HTTP 200 is not proof that the response contains valid application data.

## 21. Parallel Work and Coordination

Parallelize independent research or isolated modules, not tasks that are still changing the same contract. Before delegating, provide a bounded task specification containing context, inputs, outputs, file ownership, interface contracts, constraints, test expectations, and prohibited changes.

Integration owner responsibilities:
- Keep a single authoritative version of shared contracts.
- Detect duplicated implementations.
- Resolve incompatible naming and data formats.
- Run integration tests after merging.
- Reconcile contradictory assumptions instead of silently selecting one.
- Ensure one task does not overwrite another task's output.

If parallel execution is unavailable, use the same discipline sequentially: establish the interface first, implement one bounded component, verify it, and then move to the next.

## 22. Progress Reporting That Adds Information

A progress update should say what changed, what evidence exists, what remains, and whether a blocker affects the plan. Avoid vague messages such as “working on it” or “almost done.”

```markdown
Completed:
- Implemented the save operation in `settings.js`.

Evidence:
- Valid input persists and reloads successfully.
- Invalid input is rejected by the validator.

Remaining:
- Test storage-unavailable behavior.

Blocker:
- None.

Next:
- Run the integration test and inspect the final diff.
```

Do not claim completion based on intention, elapsed time, or the existence of a file. Completion is a state supported by evidence.

## 23. Change Control and Scope Drift

When a user adds a requirement during implementation:
1. Determine whether it changes an existing acceptance criterion or adds a new one.
2. Identify affected components and tests.
3. Check whether the new requirement conflicts with an earlier instruction.
4. Update the scope ledger and dependency order.
5. Preserve completed work that remains valid.
6. Re-test all affected behavior.

Do not blindly restart from zero when a small change is sufficient. Do not blindly patch the current design when the new requirement invalidates its foundation. Explain trade-offs when the change increases cost, risk, or delivery time.

## 24. Planning Failure Modes

- **Planning theater:** a detailed plan with no verified progress. Countermeasure: every milestone must produce an artifact or evidence.
- **Premature implementation:** code begins before essential contracts are understood. Countermeasure: identify unknowns and high-cost assumptions first.
- **Endless clarification:** asking about low-impact details that can be decided conservatively. Countermeasure: ask only questions that change the result materially.
- **Feature creep:** optional enhancements delay the requested core. Countermeasure: protect the required scope.
- **False completion:** a task is marked done after writing but before testing. Countermeasure: tie completion to acceptance evidence.
- **Unbounded research:** collecting sources without a decision question. Countermeasure: define what evidence would change the decision.
- **Checklist substitution:** checking boxes without examining whether the behavior works. Countermeasure: attach evidence to important checks.

## 25. Final Planning Quality Rubric

Score each dimension from 0 to 2:
- 0 = absent or contradicted by evidence.
- 1 = partially addressed.
- 2 = explicit and supported.

Dimensions:
1. User outcome is clear.
2. Requirements are testable.
3. Constraints and exclusions are captured.
4. Dependencies are ordered.
5. High-risk assumptions are visible.
6. Failure cases are planned.
7. Verification is proportionate.
8. Scope changes are controlled.
9. Delivery format matches the request.
10. Final claims match evidence.

A low score is a prompt to repair the plan, not a reason to inflate the score. A perfect score does not replace judgment; it is a diagnostic aid.
