---
name: Axion AI Skill
developer: Alfar
name: Complex Reasoning and Problem Solving
version: 3.0
language: English
description: Evidence-driven diagnosis, hypothesis testing, quantitative checks, and implementation debugging.
---

# Complex Reasoning and Problem Solving

## 1. Purpose

Use this skill for problems with multiple possible causes, interacting variables, incomplete evidence, or costly mistakes. The goal is not to produce an impressive explanation; the goal is to find a reliable answer or fix.

Distinguish:
- **Observation:** directly seen or measured.
- **Hypothesis:** a possible explanation.
- **Test:** an action that separates hypotheses.
- **Result:** what the test actually showed.
- **Conclusion:** the strongest statement supported by the result.

Never present a hypothesis as a proven root cause.

## 2. Problem record

```yaml
problem:
  symptom: "Observable failure"
  expected_behavior: "Expected outcome"
  actual_behavior: "Actual outcome"
  environment:
    platform: ""
    version: ""
    device_or_runtime: ""
    relevant_configuration: {}
  reproduction_steps: []
  logs_or_measurements: []
  recent_changes: []
  constraints: []
  success_condition: "Repeatable pass condition"
```

Write symptoms so another person can reproduce them. “It is broken” is not a diagnostic record. “The process exits within three seconds after entering a 3D game, but remains open on the home screen for 30 minutes” is actionable.

## 3. Reproduction and baseline

1. Preserve the original configuration.
2. Record version, hardware/runtime, settings, workload, and exact steps.
3. Repeat the failure if safe.
4. Record whether the result is consistent.
5. Capture logs and metrics before changing settings.
6. Identify a control case that succeeds.

A fix cannot be judged fairly if the baseline is unknown. If the failure is intermittent, record the number of attempts and conditions rather than claiming it always occurs.

## 4. Build a hypothesis set

Include only plausible explanations that account for the observed facts. Avoid generating a huge list of remote possibilities.

```text
H1: memory pressure
Supporting evidence: process exits only after workload increases.
Contradicting evidence: other workloads with similar memory use remain stable.
Discriminating test: monitor memory and process exit logs during the same reproduction.

H2: graphics/driver path
Supporting evidence: failure begins when 3D rendering starts.
Contradicting evidence: not yet tested with another renderer.
Discriminating test: reduce rendering load while holding other settings constant.

H3: compatibility/runtime bug
Supporting evidence: one application/version fails consistently.
Contradicting evidence: exact version and logs are not yet known.
Discriminating test: compare a supported version or inspect runtime logs.
```

Use a table when multiple hypotheses need tracking:

| Hypothesis | Evidence for | Evidence against | Discriminating test | Result |
|---|---|---|---|---|
| H1 | Specific observed signal | Counterexample | Cheapest useful test | Pending |
| H2 | Specific observed signal | Counterexample | Cheapest useful test | Pending |

Do not assign precise probabilities without data. Qualitative ranking is enough when evidence is limited.

## 5. Choose the best test

Prefer a test that:
- separates the leading hypotheses;
- changes one variable at a time;
- is low-cost and reversible;
- has an observable result;
- avoids risking user data or system stability.

Before running it, state the expected result under each hypothesis.

```text
Test: reduce resolution while keeping frame rate, workload, and runtime unchanged.
If failure disappears: graphics workload becomes more plausible, but not proven.
If failure remains: resolution alone is less likely to be the main cause.
Confounders: the setting may change memory use and GPU load simultaneously.
```

A test that changes resolution, frame rate, RAM allocation, and graphics settings simultaneously cannot isolate which change mattered.

## 6. Quantitative reasoning

State units and assumptions. Use a calculation tool or short program for arithmetic that is easy to miscalculate.

```python
def percent_change(old_value: float, new_value: float) -> float:
    if old_value == 0:
        raise ValueError("old_value must not be zero")
    return (new_value - old_value) / abs(old_value) * 100

print(f"{percent_change(40, 50):.1f}%")  # 25.0%
```

Check:
- units are consistent;
- denominators are nonzero;
- measurements cover comparable conditions;
- rounding does not change the conclusion;
- averages are not hiding outliers;
- correlation is not being mistaken for causation.

When comparing performance, report workload, duration, device state, and measurement method. A single FPS reading is not a reliable stability benchmark.

## 7. Software debugging workflow

```text
1. Reproduce the failure.
2. Capture the exact error and relevant logs.
3. Identify the smallest failing input or sequence.
4. Trace the failure to the responsible boundary.
5. State a testable hypothesis.
6. Make one targeted change.
7. Run the original reproduction.
8. Run a regression test for previously working behavior.
9. Inspect the diff for unintended changes.
10. Record the conclusion and evidence.
```

Prefer fixing the cause over hiding the exception, swallowing all errors, adding arbitrary delays, or retrying forever.

## 8. Minimal reproduction example

Suppose a function fails only for an empty list. Reduce the problem to a small test:

```python
def average(values):
    if not values:
        raise ValueError("values must not be empty")
    return sum(values) / len(values)

assert average([2, 4, 6]) == 4
try:
    average([])
except ValueError as exc:
    assert str(exc) == "values must not be empty"
else:
    raise AssertionError("Empty input should have raised ValueError")
```

The lesson is operational: reproduce the edge case, define intended behavior, implement it, and test both the normal and failing path.

## 9. Distinguish root cause from workaround

A workaround changes the conditions so the failure is less likely. A root-cause fix addresses the underlying defect. Label them honestly.

```text
Finding: reducing resolution prevents the crash in 4/5 trials.
Supported conclusion: the failure is sensitive to graphics workload.
Not yet proven: GPU memory exhaustion is the root cause.
Next test: collect memory and process logs while comparing two resolutions.
```

Do not claim certainty from a single successful run when the failure is intermittent.

## 10. Decision and trade-off analysis

For competing options, compare criteria explicitly:

```text
Option:
Correctness:
Implementation cost:
Runtime cost:
Compatibility:
Security:
Maintenance:
Failure mode:
Evidence:
Decision:
```

Weight criteria based on the user's actual priorities. Do not optimize an irrelevant metric while ignoring the requested goal.

## 11. Stop and escalation rules

Stop testing when:
- the success condition passes repeatedly;
- the original failure is no longer reproducible under the same conditions;
- relevant regression tests pass;
- remaining uncertainty is stated.

Escalate or ask for more information when:
- the environment cannot be inspected;
- the next test risks data loss or hardware damage;
- required logs or access are unavailable;
- several hypotheses remain indistinguishable;
- the result depends on unknown platform-specific behavior.

## 12. Final diagnosis format

```text
Observed:
[What happened, under what conditions]

Most likely explanation:
[Root cause if proven; otherwise a ranked hypothesis]

Evidence:
[Specific logs, tests, or measurements]

Change:
[Exact modification or recommended test]

Verification:
[Reproduction attempts and results]

Uncertainty:
[What is not yet established]
```

Do not expose hidden chain-of-thought. Provide concise reasoning summaries, explicit evidence, calculations, test results, and conclusions.


---

# Advanced Operating Specification — v4 Expansion

## 12. Formalize the Problem Before Solving It

Convert an ambiguous issue into a problem statement with observable evidence, constraints, and a success condition.

```markdown
Problem:
- What fails, for whom, and under what conditions?

Observed evidence:
- Exact message, logs, reproduction steps, measurements, or output.

Expected behavior:
- What should happen instead?

Scope:
- What is included?
- What is explicitly outside the investigation?

Constraints:
- Environment, permissions, time, compatibility, data preservation.

Success condition:
- A repeatable test that distinguishes a fix from a temporary coincidence.
```

Avoid embedding a proposed cause in the problem statement. “The cache is broken” is a hypothesis; “the page displays stale data after a successful update” is an observation.

## 13. Hypothesis Register and Discriminating Tests

List plausible explanations, the evidence supporting each, evidence against each, and the cheapest test that separates them.

| Hypothesis | Supporting evidence | Counter-evidence | Discriminating test |
|---|---|---|---|
| Input is malformed | Failure follows a specific input | Other similar inputs work | Validate input before the failing boundary |
| Dependency is unavailable | Error includes connection failure | Local path succeeds | Test connectivity and dependency health independently |
| State is stale | Refresh changes the result | Failure also occurs on a clean session | Compare stored state and rendered state |

Do not treat the table as proof. Update it as new evidence arrives. Avoid listing many near-identical hypotheses that all require the same test; group them when they are not yet distinguishable.

## 14. Debugging by Boundary and Invariant

Break a system into boundaries: input, parsing, validation, transformation, state update, persistence, network, rendering, and output. Check the contract at each boundary.

An invariant is a property that must remain true. Examples:
- A user's identifier must not change during a display-name update.
- A collision solver must not leave a movable body embedded in a solid wall after resolution.
- A successful save response must correspond to a durable or explicitly documented persistence result.
- A parsed numeric value must be finite and within the accepted range.

```python
def require_finite_number(value, name="value"):
    import math
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number

def clamp(value, low, high):
    if low > high:
        raise ValueError("low must not exceed high")
    return max(low, min(value, high))
```

Assertions are useful for internal invariants, but user-controlled input should receive explicit validation and understandable errors. Do not rely on assertions for security checks in environments where assertions can be disabled.

## 15. Minimal Reproduction and Controlled Experiments

A minimal reproduction removes unrelated complexity while preserving the failure. Record the original conditions first, then remove one factor at a time. Do not change several settings simultaneously and then attribute the outcome to one of them.

A controlled experiment has:
- One stated question.
- One variable changed at a time where practical.
- A baseline.
- A measurable outcome.
- A repeat count appropriate to variability.
- A record of environmental conditions.
- A conclusion limited to what the experiment actually supports.

For intermittent failures, record frequency and sample size. “It worked once” is weak evidence. “It passed 20 consecutive repetitions under the same recorded conditions” is stronger, though still limited to those conditions.

## 16. Quantitative Reasoning and Sanity Checks

Before trusting a calculation:
1. Identify units for every quantity.
2. Confirm dimensions are compatible.
3. Estimate the order of magnitude.
4. Check extreme and boundary values.
5. Recalculate independently when the decision is important.
6. State assumptions and rounding.
7. Distinguish measured values from estimated values.

For example, if a loop runs at 60 frames per second, the nominal frame interval is approximately \(1000/60 \approx 16.67\) milliseconds. This does not mean the system consistently renders within that interval; actual frame times vary.

Use explicit conversions and guard against division by zero, overflow, NaN, infinity, and precision loss. When a result drives a safety-sensitive or expensive decision, do not rely on a single unverified mental calculation.

## 17. Root Cause, Contributing Factor, and Workaround

Label conclusions correctly:
- **Root cause:** the underlying defect or condition that directly explains the failure.
- **Contributing factor:** a condition that makes the failure more likely or more severe.
- **Trigger:** the event that exposes the problem.
- **Workaround:** a method to avoid the symptom without removing the cause.
- **Mitigation:** a measure that reduces impact or likelihood.
- **Fix:** a change that addresses the identified cause and passes relevant verification.

If evidence only shows correlation, say so. A workaround may be valuable, but do not present it as a root-cause fix. Document side effects and conditions under which the workaround is unsafe.

## 18. Debugging Playbook

```text
1. Reproduce the failure.
2. Capture the exact symptom and environment.
3. Find the earliest boundary where actual behavior diverges from expected behavior.
4. Form a small set of competing hypotheses.
5. Select a test that separates the leading hypotheses.
6. Run the test and record the result.
7. Update the hypothesis register.
8. Implement the smallest justified change.
9. Run the original reproduction.
10. Run regression and boundary tests.
11. Inspect the diff for unrelated changes.
12. Report the cause only to the level supported by evidence.
```

If the failure cannot be reproduced, do not fabricate a successful fix. Gather logs, increase observability safely, compare known-good and failing environments, and explain the uncertainty.

## 19. When to Stop Investigating

Stop when the acceptance condition is met, relevant regression tests pass, and remaining uncertainty is proportionate to the risk. Continue when:
- Evidence contradicts the proposed explanation.
- The fix introduces a new failure.
- A high-impact edge case remains untested.
- The result depends on an undocumented assumption.
- The user asked for a deeper audit rather than a narrow fix.

Do not continue indefinitely in search of absolute certainty. State what was tested, what was not tested, and what additional evidence would materially increase confidence.

## 20. Reasoning Quality Anti-Patterns

- **Confirmation bias:** searching only for evidence that supports the first idea.
- **Premature certainty:** turning a plausible explanation into a fact.
- **Post hoc attribution:** assuming the last changed variable caused the result.
- **Symptom patching:** suppressing an error without restoring correctness.
- **Overfitting:** fixing one sample while breaking the general case.
- **Unfalsifiable hypothesis:** proposing a cause that no possible observation could disprove.
- **Complexity bias:** preferring a sophisticated solution over a simpler tested one.
- **False precision:** reporting more decimal places or confidence than the evidence warrants.
- **Silent assumption:** relying on an unstated platform or environment detail.

For each major conclusion, ask: “What observation would make this conclusion wrong?” If no answer exists, the claim may be too vague or too broad.

## 21. Technical Decision Record

```markdown
# Decision: [short title]
Date:
Context:
Options considered:
1. Option A — benefits, costs, risks.
2. Option B — benefits, costs, risks.
Decision:
Why this option fits the constraints:
Evidence:
Known limitations:
Reversal trigger:
Verification plan:
```

Use this for decisions that are expensive to reverse or likely to be revisited. Do not create bureaucratic records for trivial local choices.
